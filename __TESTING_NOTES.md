# API Testing Notes

Reference for how this repository's test suite is structured and what "a
good test" means here. Written for engineers extending the suite, and for
the downstream portal that consumes this API's HTTP responses.

This repository is the third stage in the data pipeline: the simulation
engine produces daily CSVs, the ETL transforms them into canonical
parquets, and this API reads those parquets and serves them over HTTP. The
conventions below are inherited from the sim engine's and ETL's
`__TESTING_NOTES.md` and extended for the API's position at the boundary
between server-side data and the portal's consumption.

## Established patterns

The suite uses plain `pytest` — function-style tests, the `client` fixture
in `tests/conftest.py` (a FastAPI `TestClient` with the database dependency
overridden by a `MagicMock`), `unittest.mock.patch` to isolate route tests
from the service layer, and `monkeypatch` for settings isolation. No custom
framework, no shared assertion helpers beyond what `pytest` and the
`TestClient` provide.

The env-setup block at the top of `tests/conftest.py` runs before
`app.main` is imported. After `Settings()` was moved to lazy
instantiation (resolved on first attribute access via the
`get_settings()` `lru_cache` plus a module-level `__getattr__` shim),
the env-setup block is no longer strictly required for import to
succeed — `Settings()` is now constructed only when an attribute is
first accessed, not at module import. The five `# noqa: E402` comments
remain as a defensive barrier against a future change that
re-introduces import-time work that depends on env vars; treat them as
documentation that the import order matters, not as a load-bearing
correctness guard.

Tests are graded into three categories, the shared platform vocabulary:

- **Business-correctness** — asserts specific values that are computable
  from the inputs independently of the implementation. For an HTTP API
  that has a specific meaning: a test must assert the *served value* in the
  response body — a number, a string, a status-on-condition — computed by
  hand or read off the canonical parquet, not merely that a response of
  the right shape came back. `test_api_serves_canonical_store_day_values`
  asserts that store 1 on 2024-07-01 serves `total_sales` 86429.35, a value
  read off the canonical parquet.
- **Structural** — asserts shape (status code, keys present, content-type,
  `isinstance`) but not specific served values. For route tests with the
  service mocked, this also covers forwarding checks: a test that asserts
  the route parsed `?store_id=3` into `store_id=3` and passed it to the
  service verifies dispatch wiring, not served output. Useful as an
  entry-level floor; not sufficient on its own for hot-path code.
- **Ceremony** — runs code but verifies nothing beyond "it did not raise",
  or asserts something the test setup already guarantees.

Business-correctness is the bar for hot-path code. Two techniques recur:

- **Independently-derived expectations.** Compute the expected value from
  the canonical parquet. `test_dashboard_summary_required_fields` asserts
  `total_sales == round(df["total_sales"].sum(), 2)` — the aggregate
  recomputed from the source — rather than snapshotting whatever the
  summary emitted.
- **Invariant cross-checks.** Re-derive a value at a different grain and
  compare. `test_api_cross_grain_reconciliation` sums the ten department
  `net_sales` rows for a store-day and asserts the total equals that
  store-day's `total_sales`.

## Hot-path tests

The load-bearing read/serve logic and the tests that hold it.

**Read pipeline** (canonical parquet -> DataFrame):

- **Parquet reading** — `test_grocery_service.py`. `load_store_metrics_df`
  and `load_anomaly_flags_df` read the resolved parquet and return a
  DataFrame with the canonical schema, the canonical row count (2944 store
  metrics, 178 anomaly flags), and `datetime.date` objects in the `date`
  column. The missing-path branch raises `FileNotFoundError`
  (`test_load_*_raises_when_path_missing`).
- **Schema enforcement** — `test_etl_contract.py::
  test_api_dim_stores_enforces_string_identifier_schema`. `zip` and
  `county_fips` are stored as int64 in the parquet and coerced to
  5-character zero-padded strings by `get_dim_stores`; the contract test
  runs that coercion against the real parquet. `open_date` is coerced from
  string storage to a typed `date`.

**Serve pipeline** (DataFrame -> JSON response):

- **Filtering** — `test_grocery_service.py`. `get_store_metrics` and
  `get_anomalies` apply date-range, store, severity, and rule filters; the
  filtered total matches an independently counted row set.
- **Pagination** — `test_get_store_metrics_pagination_honored` and
  `test_get_anomalies_pagination_honored` assert the exact `(date,
  store_id)` window each page returns under the service's
  `(date, store_id[, rule_id])` sort. The 200-row endpoint limit is
  enforced by `Query(le=200)` and checked by the `*_limit_too_large`
  route tests.
- **Endpoint contracts** — each route file has a test module asserting the
  envelope shape (`total`, `limit`, `offset`, `items`) or, for `/dim-stores`,
  the flat-array shape. `test_etl_contract.py` pins specific served values
  for `/store-metrics`, `/department-metrics`, and `/dim-stores`.

**Dual-mode operation:**

- **Mode detection** — `test_health.py::test_health_grocery_mode_is_*`.
  `/health` reports `grocery_pipeline.mode` as `offline` when no `*_PATH`
  is set and `online` when all four resolve to readable files.
- **Mode equivalence** — `test_etl_contract.py::
  test_offline_and_online_modes_serve_identical_output`. See "Dual-mode
  considerations" below.

**Cross-cutting:**

- **Error handling** — `404` for an unknown series, `400` for an inverted
  dashboard date range, `422` for malformed query parameters. These are
  structural (a rejected request has no served value to assert) but are
  the correct test for input validation.
- **Request correlation** — `test_request_correlation.py`. Every response
  carries an `X-Request-ID`; an incoming header is echoed back; absent a
  header each request gets a unique id.

## Upstream contract tests

`tests/test_etl_contract.py` pins the contract between the ETL's canonical
parquet output and the API's read/serve pipeline. It is the first test file
that exercises the API against genuine upstream data end to end rather than
against a mocked service.

The fixtures are the parquets already bundled at `app/fixtures/`
(`store_daily_metrics`, `department_daily_metrics`, `dim_stores`,
`anomaly_flags`). These are byte-identical — verified by SHA-256 — with the
ETL's canonical output at `data/processed/canonical/`, so no separate
contract fixture is captured: the bundled parquets *are* the upstream
contract. The ETL produces byte-identical parquet output for identical
input, so a committed parquet is a stable contract input.

The five tests assert:

- **`test_bundled_fixture_matches_canonical_sha256`** — each of the four
  bundled parquets' SHA-256 hashes match a hardcoded reference captured
  at the upstream ETL boundary. Drift in any direction — stale fixture,
  corrupted copy, inadvertent re-encode — fails the test with the
  offending filename in the parametrize ID.
- **`test_api_serves_canonical_store_day_values`** — `/store-metrics` for a
  known store-day returns the exact `total_sales` and `transaction_count`
  read off the canonical parquet.
- **`test_api_cross_grain_reconciliation`** — the ten department
  `net_sales` rows for a store-day sum to that store-day's `total_sales`.
  The two endpoints read different parquets at different grains, so
  agreement is a genuine cross-grain check.
- **`test_api_dim_stores_enforces_string_identifier_schema`** — `/dim-stores`
  serves `zip` and `county_fips` as 5-character zero-padded strings,
  exercising the int64 -> string coercion against the real parquet.
- **`test_offline_and_online_modes_serve_identical_output`** — see below.

A failure here after regenerating the fixtures means the ETL's output
changed in a way the API must account for, or the API's read/serve pipeline
silently transformed a value — which is the signal the contract test exists
to surface.

## Dual-mode considerations

The API resolves each grocery parquet through a four-path lookup
(`settings.resolved_*_path`): if the configured `*_PATH` points at a
readable file it is used (online mode), otherwise the bundled `app/fixtures`
parquet is used (offline mode). `/health` reports the mode via
`grocery_pipeline.mode`.

`test_offline_and_online_modes_serve_identical_output` verifies the
contract that both modes produce identical output for identical input. It
serves the bundled parquets in offline mode, copies those same parquets to
a temporary directory and points the four `*_PATH` settings at the copies
to flip resolution onto the live branch, and asserts every endpoint returns
identical responses across the two modes — with `/health` reporting the
mode it is actually operating in.

Coverage by mode after this pass:

- **Offline mode** — well covered. Every `test_grocery_service.py` test and
  three of the four contract tests run against the bundled fixtures.
- **Online mode** — mode *detection* was already covered
  (`test_health_grocery_mode_is_online_when_paths_exist`, which uses empty
  placeholder files). Online-mode *serving* — actually reading and serving
  data through a resolved live path — was untested before this pass;
  `test_offline_and_online_modes_serve_identical_output` now exercises it.
- The silent-fallback risk (a misconfigured `*_PATH` resolving quietly to
  fixtures) is mitigated in production by the startup
  `grocery_data_source_fallback` warning log; it is not separately tested
  here and is a candidate for a future targeted test.

## Test categories observed

Snapshot from the test-quality pass on 2026-05-21 — the suite held 126
tests at the start and 130 at the end of that pass. Classification:

| Category             | At start | After pass |
|----------------------|----------|------------|
| Business-correctness | 38       | 49         |
| Structural           | 86       | 79         |
| Ceremony             | 2        | 2          |
| Uncategorizable      | 0        | 0          |
| Total                | 126      | 130        |

Current suite size (verified 2026-05-27): 160 tests. Six were added in
the canonical-refresh pass: four parametrized cases pinning each bundled
fixture's SHA-256 to the upstream ETL canonical (in
`test_etl_contract.py`, business-correctness — each asserts an
independently captured hash, not a re-hash of the same bytes), and two
parametrized cases extending the route-level `rule_id` matrix in
`test_anomalies.py` to cover `department_coverage` and
`revenue_zscore_28d`. A follow-on commit pinned the macro DB probe
warning to carry no traceback (business-correctness, asserts the
formatted log record), bringing the total to 142. The
operational-seams pass added nine `test_request_correlation.py` cases
covering X-Request-ID header validation (oversized, malformed,
uppercase, length-cap-overflow shapes), bringing the total to 151;
the same pass added three `test_config.py` cases pinning the lazy
Settings lifecycle and the module-level import shim, bringing the
total to 154; the same pass added six `test_grocery_service.py` cases
pinning parquet read caching (per-loader cache, cache-clear helper,
and cache re-keying on resolved-path change), bringing the total to
160. Five earlier
additions live in `test_health.py`,
covering the per-pipeline reporting shape introduced when `/health` was
split into independent grocery and macro sub-objects; those are
structural — the endpoint's status and reason fields are not derived
quantities. The split above remains directionally accurate; see
`README.md` for the current per-file breakdown.

The suite is structural-heavy by construction: most route test modules mock
the service layer, so they can only assert dispatch wiring and response
shape, not served data values. The genuine business-correctness density
sits in `test_grocery_service.py`, which runs against the bundled parquets.

This pass converted seven structural tests covering read/serve hot paths
into business-correctness tests (the two parquet loaders, the two
`returns_total_and_items` checks, the two pagination checks, and the
dashboard-summary totals) and added four contract tests, bringing the suite
to 130. The structural/business split involves judgment at the margin — a
row-count assertion and an exact-value assertion sit close together — but
the direction of travel is what matters: read/serve hot-path code earns
value assertions.

## Known weak areas

Tests left as structural or ceremony, with the reason each was not
strengthened:

- `test_observability.py::TestConfigureLogging::
  test_default_invocation_runs_without_error` — ceremony. It exercises
  structlog configuration, which is not a data hot path. Left in place,
  matching the sim engine and ETL passes' decision on their analogous
  tests.
- `test_dashboard.py::test_dashboard_top_stores_capped_at_5` — ceremony at
  the route layer. The service is mocked with a list already capped at
  five rows, so the `len <= 5` assertion cannot fail regardless of route
  behavior. The real cap-and-sort logic is covered by
  `test_grocery_service.py::test_dashboard_summary_top_stores_capped_at_5`,
  which runs against the parquet. Left in place — this pass deletes no
  tests.
- The route test modules (`test_store_metrics`, `test_department_metrics`,
  `test_anomalies`, `test_dashboard`, and the economic `test_series`,
  `test_metrics`, `test_insights`) are predominantly structural: with the
  service mocked, they verify query-parameter parsing, dispatch, envelope
  shape, and validation rejection. That is a legitimate contract for a
  route handler — its job is parse, dispatch, and shape — and the
  end-to-end served-value coverage is supplied by `test_etl_contract.py`
  rather than by un-mocking every route test. The economic endpoints are
  database-backed and outside this pass's grocery-parquet hot-path focus;
  their route tests remain structural.

No production bugs were discovered while strengthening the targeted tests.
Every strengthened test passes against the current code. One documentation
drift was noted and addressed in a follow-up commit (700806c): the
`app/api/routes/department_metrics.py` docstring previously described the
canonical dataset as "14,706 rows covering 2025-07-01 through 2025-12-31";
it now reports 29,414 rows covering 2024-07-01 through 2025-12-31, in line
with the bundled parquet.

## For downstream phases

The portal consumes this API's HTTP responses and should carry the same
conventions:

- **Contract testing works layer by layer.** The ETL pins the sim engine ->
  ETL contract; this repo pins the ETL -> API contract with
  `test_etl_contract.py`. The portal should pin the API -> portal contract
  the same way: stand up a known API response (or capture one), run it
  through the portal's data layer, and assert specific rendered or derived
  values.
- **The canonical parquet is the same fixture all the way down.** The
  bundled `app/fixtures` parquets are byte-identical with the ETL's
  canonical output, which is byte-identical for a given sim engine
  `(seed, date)`. A value asserted in the ETL's contract test, this repo's
  contract test, and a portal contract test all trace to the same upstream
  artifact — that continuity is what makes the test chain meaningful.
- **Business-correctness means independently-derived expectations.** A test
  that asserts a served or rendered value should compute the expectation
  from the input by hand or from a spec, not snapshot whatever the code
  currently returns. A snapshot is a regression guard, not a correctness
  test.
- **Dual-mode equivalence is a reusable pattern.** Where a layer can read
  from more than one source for the same logical data, assert that the
  sources produce identical output for identical input, and assert that any
  mode indicator (here, `/health`'s `grocery_pipeline.mode`) reports the mode the
  layer is actually operating in.
- **The three-category vocabulary** — business-correctness, structural,
  ceremony — is the shared language for grading test strength across the
  platform. Hot-path code earns value assertions; structural coverage is
  acceptable only for non-load-bearing surfaces.
