# Economic Data API

A read-only REST API that exposes economic time-series data and grocery analytics. Built with FastAPI and SQLAlchemy. The macro side reads from Postgres (the upstream `economic-data-etl` repo's load target); the grocery side reads from parquet files (also produced by `economic-data-etl`). The service is one of four repositories in the Knot Shore Grocery analytics platform — it sits between the ETL pipeline and the consumer-facing portal.

## Where this fits in the platform

```
knot-shore-grocery-simulation-engine    →    economic-data-etl    →    economic-data-api    →    knot-shore-portal
sim data generator                           ingestion + detection      this repo                  dashboards
                                                                       (service layer)             + docs hub
```

Reader-grade documentation for this API — endpoint contracts, dual-mode operation, observability stack — lives at the portal's [`/about/api`](https://github.com/Caseykelly87/knot-shore-portal) page. The platform-wide architectural narrative is at [`/about/architecture`](https://github.com/Caseykelly87/knot-shore-portal); decision records (including the `resolved_*_path` pattern, the 200-row pagination cap, the schema discipline) are at [`/about/decisions`](https://github.com/Caseykelly87/knot-shore-portal).

## Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12+ |
| Web framework | FastAPI |
| ORM | SQLAlchemy 2.0 (read-only) |
| Validation | Pydantic v2 |
| Database | PostgreSQL (macro side) |
| Parquet IO | pandas + pyarrow (grocery side) |
| Observability | structlog, prometheus-fastapi-instrumentator |
| Testing | pytest + httpx |

---

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in your database credentials (see Environment Variables below)
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_HOST` | Yes | — | PostgreSQL host (macro side only) |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_NAME` | Yes | — | Database name |
| `DB_USER` | Yes | — | Database user |
| `DB_PASSWORD` | Yes | — | Database password |
| `API_ENV` | No | `development` | Environment label |
| `API_TITLE` | No | `Economic Data API` | Title shown in docs |
| `API_VERSION` | No | `1.0.0` | Version shown in docs |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `LOG_FORMAT` | No | auto | `console` (colored text) or `json`. Auto-detects: console when stdout is a tty, json when piped or redirected. |
| `STORE_METRICS_PATH` | No | — | Path to live `store_daily_metrics.parquet` from the upstream ETL. Falls back to bundled fixture if unset or unreadable. |
| `ANOMALY_FLAGS_PATH` | No | — | Path to live `anomaly_flags.parquet` from the upstream ETL. Falls back to bundled fixture if unset or unreadable. |
| `DEPARTMENT_METRICS_PATH` | No | — | Path to live `department_daily_metrics.parquet` from the upstream ETL. Falls back to bundled fixture if unset or unreadable. |
| `DIM_STORES_PATH` | No | — | Path to live `dim_stores.parquet` from the upstream ETL. Falls back to bundled fixture if unset or unreadable. |
| `GROCERY_FIXTURES_DIR` | No | `app/fixtures` | Directory where bundled fixtures live. Used as the fallback source. |

The four `*_PATH` env vars are independent — each path resolves to live or fixture per request via a property on the settings object. Mode detection (live vs fixture) reported by `/health` is `live` only when **all four** paths point at readable files; otherwise `fixtures`.

---

## Running

```bash
uvicorn app.main:app --reload
```

- API: `http://localhost:8000`
- Interactive docs (Swagger UI): `http://localhost:8000/docs`
- Alternative docs (ReDoc): `http://localhost:8000/redoc`

---

## Logging

The API emits structured logs via [structlog](https://www.structlog.org/). Output is human-readable colored text when stdout is a tty, single-line JSON otherwise. Format and verbosity are controlled by environment variables:

| Variable | Values | Default |
|---|---|---|
| `LOG_LEVEL` | `debug`, `info`, `warning`, `error`, `critical` | `info` |
| `LOG_FORMAT` | `console`, `json` | auto (console if tty, else json) |

The structlog configurator (`app/core/logging_config.py`) chains processors that add a timestamp, the request-bound correlation ID, the log level, and the calling logger's name. The chain includes `structlog.stdlib.ExtraAdder()` so calls like `logging.info("foo", extra={"k": "v"})` propagate the structured fields through to the rendered output.

### Request correlation

Every inbound HTTP request is tagged with a UUID. The middleware:

- Generates a UUID per request, OR uses the value of the incoming `X-Request-ID` header if the caller provides one.
- Binds the ID to structlog's contextvars so every log line emitted during the request lifetime includes a `request_id` field.
- Echoes the ID on the response's `X-Request-ID` header so callers can correlate from their side.

Example: when the portal calls `/store-metrics`, it can pass `X-Request-ID: <its-own-id>` and the API's logs for that request will show the same `request_id`, making it possible to trace one user's flow across portal logs and API logs by grepping for one UUID.

### Output examples

Console mode (default in a terminal):

```
2025-12-31T17:34:42.118Z [info     ] request_handled                request_id=8c3f... method=GET path=/store-metrics status_code=200 duration_ms=12.4
```

JSON mode (default when piped, or when `LOG_FORMAT=json`):

```json
{"event": "request_handled", "request_id": "8c3f...", "method": "GET", "path": "/store-metrics", "status_code": 200, "duration_ms": 12.4, "level": "info", "timestamp": "2025-12-31T17:34:42.118Z"}
```

To run with debug-level logs:

```bash
LOG_LEVEL=debug uvicorn app.main:app --port 8000
```

To capture structured logs for offline analysis:

```bash
LOG_FORMAT=json uvicorn app.main:app --port 8000 > api.log 2>&1
```

---

## Metrics

The API exposes a `/metrics` endpoint in Prometheus text format. Any Prometheus-compatible scraper can poll this endpoint to collect time-series data on request rates, latencies, and custom counters.

```bash
curl http://localhost:8000/metrics
```

### Auto-instrumented HTTP metrics

The [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator) library produces three standard metrics for every route:

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | Counter | `method`, `handler`, `status` |
| `http_request_duration_seconds` | Histogram | `method`, `handler` |
| `http_requests_inprogress` | Gauge | `method`, `handler` |

### Custom counters

Two custom counters track operational facts specific to the grocery endpoints:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `grocery_data_source_total` | Counter | `source` | Increments per grocery request. `source` is `fixtures` or `live` based on the four `*_PATH` env var configuration. |
| `service_call_total` | Counter | `service` | Increments per grocery service-layer call. `service` is the function name (e.g. `get_store_metrics`, `get_anomalies`, `get_dashboard_summary`, `get_department_metrics`, `get_dim_stores`). |

Both counters increment at the same call sites as the corresponding structured log events (`service_call_started` and `service_call_completed`). Logs give per-call detail with the request_id; metrics give aggregate rates that scrapers can plot over time.

### Example output

```
# HELP http_requests_total Total number of requests by method, status and handler.
# TYPE http_requests_total counter
http_requests_total{handler="/store-metrics",method="GET",status="2xx"} 5.0

# HELP grocery_data_source_total Number of grocery requests served, labeled by data source.
# TYPE grocery_data_source_total counter
grocery_data_source_total{source="fixtures"} 5.0

# HELP service_call_total Number of grocery service function calls, labeled by service name.
# TYPE service_call_total counter
service_call_total{service="get_store_metrics"} 3.0
service_call_total{service="get_anomalies"} 1.0
service_call_total{service="get_dashboard_summary"} 1.0
```

### Authentication

The `/metrics` endpoint is unauthenticated. Production deployments should restrict access via firewall rules, an authenticating reverse proxy, or a service mesh — Prometheus convention is metrics endpoints sit inside trusted networks.

---

## Testing

```bash
pytest                  # all 122 tests
pytest -v               # verbose
pytest tests/test_metrics.py   # single file
pytest --cov=app        # with coverage
```

The test suite makes no live database connections and no network calls. Service-layer functions are patched via `unittest.mock.patch` so endpoint tests assert on response shapes without touching parquet files or the database. Service-layer tests use synthetic DataFrames built in-memory.

The 13 test files:

| File | Tests | Coverage |
|---|---:|---|
| `test_health.py` | 10 | `/health` endpoint, four-path live-mode contract |
| `test_series.py` | 13 | `/series` and `/series/{series_id}` |
| `test_metrics.py` | 13 | `/metrics/inflation`, `/metrics/unemployment`, `/metrics/gdp` |
| `test_insights.py` | 4 | `/insights/summary` |
| `test_grocery_service.py` | 24 | Service layer — parquet IO, filtering, pagination |
| `test_store_metrics.py` | 10 | `/store-metrics` endpoint and pagination envelope |
| `test_anomalies.py` | 13 | `/anomalies` endpoint, all filter parameters |
| `test_dashboard.py` | 9 | `/dashboard-summary` envelope and aggregation |
| `test_department_metrics.py` | 9 | `/department-metrics` endpoint and filters |
| `test_dim_stores.py` | 7 | `/dim-stores` endpoint, ZIP/FIPS string coercion |
| `test_observability.py` | 4 | structlog configurator, ExtraAdder bridge |
| `test_prometheus_metrics.py` | 3 | `/metrics` endpoint, custom counter wiring |
| `test_request_correlation.py` | 3 | X-Request-ID middleware, contextvars binding |

The Pydantic schemas are themselves a form of test: any service function that returns data not matching its declared schema fails serialization, surfacing the contract violation immediately.

---

## Endpoints

### Health

#### `GET /health`

Liveness and readiness check. Pings the database with `SELECT 1`. Reports `data_source` (`live` or `fixtures`) for the grocery side based on whether all four `*_PATH` env vars resolve to readable files.

**Response** `200`

```json
{
  "status": "ok",
  "version": "1.0.0",
  "db": "connected",
  "data_source": "fixtures"
}
```

**Response** `503` — when the database is unreachable

```json
{
  "status": "degraded",
  "version": "1.0.0",
  "db": "unavailable",
  "data_source": "fixtures"
}
```

The 503 form lets load balancers and orchestrators route traffic away from unhealthy instances. `data_source` continues to reflect grocery `*_PATH` configuration regardless of database state, so a 503 still tells you whether the grocery side is on live or fixture data.

### Series

#### `GET /series`

List all available series with metadata (id, name, source, latest date, latest value).

#### `GET /series/{series_id}`

Metadata and full observation history for a single series, optionally filtered by date range.

**Path parameters**

| Param | Description |
|---|---|
| `series_id` | Series identifier, e.g. `CPIAUCSL` |

**Query parameters**

| Param | Type | Description |
|---|---|---|
| `start_date` | `YYYY-MM-DD` | Return observations on or after this date |
| `end_date` | `YYYY-MM-DD` | Return observations on or before this date |

**Responses**

| Status | Condition |
|---|---|
| `200` | Series found |
| `404` | No series with that `series_id` |
| `422` | Invalid date format |

**Response** `200`

```json
{
  "series_id": "CPIAUCSL",
  "series_name": "CPI_URBAN",
  "source": "BLS",
  "observations": [
    { "observation_date": "2024-01-01", "value": 310.326 }
  ]
}
```

---

### Metrics (macro)

All metric endpoints share the same query parameters and response structure.

**Shared query parameters**

| Param | Type | Description |
|---|---|---|
| `start_date` | `YYYY-MM-DD` | Filter observations on or after this date |
| `end_date` | `YYYY-MM-DD` | Filter observations on or before this date |
| `series_id` | string | Return only the specified series |

**Shared response shape** (list of series objects)

```json
[
  {
    "series_id": "CPIAUCSL",
    "series_name": "CPI_URBAN",
    "source": "BLS",
    "latest_date": "2026-02-01",
    "latest_value": 315.58,
    "observations": [
      { "observation_date": "2024-01-01", "value": 310.326 }
    ]
  }
]
```

#### `GET /metrics/inflation`

Inflation-related series (e.g. CPI, gas prices) from `public_analytics.mart_inflation`.

#### `GET /metrics/unemployment`

Labor market series (e.g. unemployment rate, average wages) from `public_analytics.mart_labor_market`.

#### `GET /metrics/gdp`

GDP-related series (e.g. real GDP) from `public_analytics.mart_gdp`.

---

### Insights

#### `GET /insights/summary`

Pre-aggregated snapshot of all key indicators from `public_analytics.mart_economic_summary`. Returns the latest value and date for every tracked series — useful for dashboards.

**Response** `200`

```json
{
  "indicators": [
    {
      "series_id": "CES0500000003",
      "series_name": "AVG_WAGES",
      "source": "BLS",
      "latest_date": "2026-02-01",
      "latest_value": 37.32
    }
  ]
}
```

---

### Grocery data endpoints

Five endpoints expose the upstream ETL's parquet outputs as JSON. They power the Knot Shore portal's dashboard, store drilldown, and exception triage views.

#### `GET /store-metrics`

Paginated store-day metric rows. Filterable by `start_date`, `end_date`, `store_id`. Pagination via `limit` (1–200, default 50) and `offset`. Standard envelope (`total`, `limit`, `offset`, `items`).

#### `GET /anomalies`

Paginated detection flags. Filterable by `start_date`, `end_date`, `store_id`, `severity_level` (`info` / `warning` / `critical`), and `rule_id` (`revenue_band` / `labor_pct_band` / `avg_ticket_band` / `transactions_band` / `yoy_comp`). Standard envelope.

#### `GET /dashboard-summary`

Single-shot KPI overview over a required `start_date` / `end_date` window: total sales, total transactions, average labor pct, top-5 stores by revenue, exception counts by severity (always all three levels reported, including zero counts), and a daily sales trend series.

#### `GET /department-metrics`

Paginated department-grain rows at the store-day-department grain. Filterable by `start_date`, `end_date`, `store_id` (1–8), and `department_id` (1–10). Standard envelope.

Query parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `start_date` | date (YYYY-MM-DD) | none | Filter rows on or after this date |
| `end_date` | date (YYYY-MM-DD) | none | Filter rows on or before this date |
| `store_id` | int (1–8) | none | Filter to a single store |
| `department_id` | int (1–10) | none | Filter to a single department |
| `limit` | int (1–200) | 50 | Number of rows to return |
| `offset` | int (≥0) | 0 | Number of rows to skip |

Example:

```bash
# All departments at store 3 for July 2025
curl -s "http://localhost:8000/department-metrics?store_id=3&start_date=2025-07-01&end_date=2025-07-31"
```

Response:

```json
{
  "total": 310,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "date": "2025-07-01",
      "store_id": 3,
      "department_id": 1,
      "net_sales": 9847.22,
      "transactions": 252,
      "units_sold": 814,
      "gross_margin_pct": 0.46
    }
  ]
}
```

#### `GET /dim-stores`

Reference data for the 8 stores in the grocery dataset. Returns a flat array (no pagination — the dataset is tiny). Rows are sorted by `store_id`. No query parameters.

Example:

```bash
curl -s "http://localhost:8000/dim-stores"
```

Response:

```json
[
  {
    "store_id": 1,
    "store_name": "Knot Shore — Kirkwood",
    "address": "10250 Manchester Rd",
    "city": "Kirkwood",
    "zip": "63122",
    "county_fips": "29189",
    "trade_area_profile": "suburban-family",
    "sqft": 45000,
    "open_date": "2009-04-15",
    "base_daily_revenue": 95000.0
  }
]
```

Field notes:

- `zip` and `county_fips` are 5-character zero-padded strings, not integers. They are identifiers; arithmetic on them is meaningless. Storing as strings preserves leading zeros for entries outside the current St. Louis dataset.
- `trade_area_profile` is one of `suburban-family`, `urban-dense`, or `value-market`.
- `open_date` is ISO format (YYYY-MM-DD).

#### Live mode vs fixture mode

The API runs in one of two modes for the grocery endpoints, automatically detected at request time:

- **Live** — all four of `STORE_METRICS_PATH`, `ANOMALY_FLAGS_PATH`, `DEPARTMENT_METRICS_PATH`, and `DIM_STORES_PATH` env vars point at readable parquet files (typically the ETL's `data/processed/canonical/` output, or a mounted volume in a container deployment). `/health` reports `data_source: "live"`.
- **Fixture** — one or more of those env vars are unset or point at unreadable paths. The API serves the bundled fixture parquets at `app/fixtures/`. The startup log prints a WARNING and `/health` reports `data_source: "fixtures"`.

Fixture mode is the default for fresh clones — the API works out of the box without any configuration.

The four paths resolve independently per request via `Settings.resolved_*_path` properties. A misconfiguration where one path is set and three are missing will fall back to fixtures globally; the live-vs-fixtures binary applies to the whole grocery surface.

#### Refreshing bundled demo fixtures

The fixtures in `app/fixtures/` (`store_daily_metrics.parquet`, `anomaly_flags.parquet`, `department_daily_metrics.parquet`, `dim_stores.parquet`) are byte-identical copies of the canonical pipeline output committed at `data/processed/canonical/` in the upstream `economic-data-etl` repository. They are produced by running the actual sim engine and ETL pipeline end-to-end against the canonical paired-year window — they are not separately generated synthetic data.

Current canonical contents:

| File | Rows × Cols | Notes |
|---|---:|---|
| `store_daily_metrics.parquet` | 2,944 × 6 | 8 stores × 184 days × 2 years (2024 + 2025) |
| `department_daily_metrics.parquet` | 29,414 × 7 | Same window across 10 departments per store-day |
| `anomaly_flags.parquet` | 983 × 9 | 950 info, 33 warning, 0 critical |
| `dim_stores.parquet` | 8 × 10 | One row per store |

The paired-year canonical (added in a recent phase) contains both 2024 and 2025 windows. Filtering `store_daily_metrics.parquet` to the 2025 window yields 1,472 rows (the original single-year canonical baseline). The 2024 window enables year-over-year comparison views in the portal's store drilldown via the existing `start_date` / `end_date` filters; no new endpoints were needed.

To refresh: regenerate the canonical parquets in the upstream ETL repo (`scripts/build_canonical_fixtures.py` there), then copy the resulting files into this repo's `app/fixtures/` and commit. The upstream pipeline is byte-deterministic, so successive regenerations against the same window produce identical bytes.

#### Planned: `GET /contextual-insights`

Originally scoped for this MVP and deferred pending portal-side requirement clarification. Will join macroeconomic context (CPI, unemployment) onto Knot Shore performance to surface "exceptions during economic stress" narratives.

---

## Architecture

```
app/
├── main.py                     # App factory, middleware, health route, error handler
├── core/
│   ├── config.py               # Settings loaded from environment / .env; resolved_*_path properties
│   ├── logging_config.py       # Structlog configurator (called once at startup)
│   └── metrics.py              # Custom Prometheus counters on the prometheus_client default registry
├── api/routes/
│   ├── series.py               # /series endpoints
│   ├── metrics.py              # /metrics/* endpoints (macro)
│   ├── insights.py             # /insights endpoints
│   ├── store_metrics.py        # /store-metrics endpoint
│   ├── anomalies.py            # /anomalies endpoint
│   ├── dashboard.py            # /dashboard-summary endpoint
│   ├── department_metrics.py   # /department-metrics endpoint
│   └── dim_stores.py           # /dim-stores endpoint
├── db/
│   └── session.py              # SQLAlchemy engine factory and session dependency
├── fixtures/                   # Bundled demo parquets (copies of upstream ETL canonical output)
├── models/
│   └── economic.py             # SQLAlchemy ORM models (read-only, no migrations)
├── schemas/
│   ├── economic.py             # Pydantic schemas for series/metrics/insights
│   └── grocery.py              # Pydantic schemas for grocery endpoints
└── services/
    ├── economic.py             # Query logic for postgres-backed endpoints
    └── grocery.py              # Parquet IO + aggregation for grocery endpoints

scripts/
└── inspect_schema.py           # Ad-hoc DB schema inspection helper

tests/
├── conftest.py                 # Client fixture with mocked DB session
├── test_health.py              # /health endpoint, four-path live-mode contract
├── test_series.py              # /series and /series/{series_id}
├── test_metrics.py             # /metrics/inflation, /metrics/unemployment, /metrics/gdp
├── test_insights.py            # /insights/summary
├── test_grocery_service.py     # Service layer — parquet io, filtering, pagination
├── test_store_metrics.py       # /store-metrics endpoint and pagination envelope
├── test_anomalies.py           # /anomalies endpoint, all filter parameters
├── test_dashboard.py           # /dashboard-summary envelope and aggregation
├── test_department_metrics.py  # /department-metrics endpoint and filters
├── test_dim_stores.py          # /dim-stores endpoint, ZIP/FIPS string coercion
├── test_observability.py       # Structlog configurator, ExtraAdder bridge
├── test_prometheus_metrics.py  # /metrics endpoint, custom counter wiring
└── test_request_correlation.py # X-Request-ID middleware, contextvars binding
```

### Database schemas

| Schema | Purpose |
|---|---|
| `raw` | Source-of-truth tables populated by the ETL pipeline |
| `public_analytics` | Pre-aggregated mart tables optimised for API reads |

This API reads from both schemas but never writes. Adding a new data source means updating the ETL pipeline; the API automatically surfaces the new data through the existing endpoints.

---

## Adjacent repositories

- [`knot-shore-grocery-simulation-engine`](https://github.com/Caseykelly87/Knot-shore-grocery-simulation-engine) — generates the synthetic CSV data the ETL ingests; produces the data this API ultimately serves through its grocery endpoints.
- [`economic-data-etl`](https://github.com/Caseykelly87/economic-data-etl) — produces the canonical parquet artifacts this API serves. The bundled fixtures at `app/fixtures/` are byte-identical copies of the ETL's `data/processed/canonical/` directory.
- [`knot-shore-portal`](https://github.com/Caseykelly87/knot-shore-portal) — primary client of this API; Next.js 14 application with three primary dashboards and the platform's `/about/*` documentation hub. The reader-grade narrative for this API repo lives at [`/about/api`](https://github.com/Caseykelly87/knot-shore-portal/blob/main/app/about/api/page.tsx).

---

## Deployment

The repository ships a `Dockerfile` that produces a self-contained image of the API. The image bundles the grocery parquet fixtures from `app/fixtures/`, so the grocery routes (`/store-metrics`, `/anomalies`, `/department-metrics`, `/dim-stores`, `/dashboard-summary`) work as soon as the container starts. The macro routes (`/series`, `/metrics/*`, `/insights/*`) require a reachable PostgreSQL — connection details are read from the `DB_*` environment variables at runtime, never baked into the image.

The Dockerfile is target-agnostic: it runs on plain Docker hosts, Railway, Render, Fly.io, AWS ECS, Google Cloud Run, or Kubernetes. Port and worker count are configurable via `PORT` and `WORKERS` env vars so platform-as-a-service injection patterns work without modification.

### Building the image

```bash
docker build -t economic-data-api .
```

On Apple Silicon hosts deploying to amd64 targets, use buildx:

```bash
docker buildx build --platform linux/amd64 -t economic-data-api .
```

### Running with a local PostgreSQL via docker-compose

`docker-compose.smoke.yml` brings the API up alongside a throwaway `postgres:16-alpine` seeded with empty mart schemas. It is the simplest local-dev path and is also what the smoke test uses.

```bash
docker compose -f docker-compose.smoke.yml up -d
curl http://localhost:8000/health
docker compose -f docker-compose.smoke.yml down -v
```

The compose stack creates empty `raw` and `public_analytics` schemas so macro routes return 200 with an empty list rather than 500 from missing tables. For a populated database, use the `economic-data-etl` upstream pipeline.

### Running against an external PostgreSQL

```bash
docker run -p 8000:8000 \
    -e DB_HOST=<host> \
    -e DB_PORT=5432 \
    -e DB_NAME=<db> \
    -e DB_USER=<user> \
    -e DB_PASSWORD=<password> \
    economic-data-api
```

The four grocery `*_PATH` env vars are optional. When unset, the container serves the bundled `app/fixtures/` parquets. Point them at mounted live parquet paths to serve the upstream ETL's canonical output instead.

### Running the smoke test

```bash
./scripts/smoke_test_container.sh
```

Builds the image, brings the compose stack up, polls `/health`, exercises the macro and grocery routes against the running container, and tears the stack down. Setting `API_URL=http://host:port` skips the build/up/down and runs only the endpoint checks against an existing URL.

### Environment variables

The five `DB_*` variables are required for the container to start (the Settings model in `app/core/config.py` has no defaults for them and the SQLAlchemy engine is created at import time). The rest are optional with the defaults shown.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_HOST` | Yes | — | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_NAME` | Yes | — | Database name |
| `DB_USER` | Yes | — | Database user |
| `DB_PASSWORD` | Yes | — | Database password |
| `API_ENV` | No | `development` | Environment label exposed via `/health` |
| `API_TITLE` | No | `Economic Data API` | Title shown in Swagger and ReDoc |
| `API_VERSION` | No | `1.0.0` | Version shown in docs and `/health` |
| `LOG_LEVEL` | No | `INFO` | Verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | No | auto | `console` (colored) or `json`. Auto-detects: console when stdout is a tty, json when piped. |
| `CORS_ORIGINS` | No | `*` | Comma-separated allowed origins, or `*` for any |
| `STORE_METRICS_PATH` | No | bundled fixture | Path to live `store_daily_metrics.parquet` |
| `ANOMALY_FLAGS_PATH` | No | bundled fixture | Path to live `anomaly_flags.parquet` |
| `DEPARTMENT_METRICS_PATH` | No | bundled fixture | Path to live `department_daily_metrics.parquet` |
| `DIM_STORES_PATH` | No | bundled fixture | Path to live `dim_stores.parquet` |
| `GROCERY_FIXTURES_DIR` | No | `app/fixtures` | Directory bundled fixtures are read from |
| `PORT` | No | `8000` | Port uvicorn binds to inside the container |
| `WORKERS` | No | `1` | Number of uvicorn worker processes |

### Deployment-target notes

- **Railway** — Set the five `DB_*` variables in the project's environment. Railway injects `PORT`; the container uses it automatically. Point a Railway-managed Postgres add-on at `DB_HOST` etc., or supply credentials for an external database.
- **Render** — Set `PORT=10000` (Render's expected internal port) or accept the value Render injects. Configure `DB_*` from a Render Postgres or external service via the dashboard's environment-variables panel.
- **Fly.io** — In `fly.toml` set `internal_port = 8000` (or whatever `PORT` is set to). Fly Postgres or Supabase makes a reasonable backing store; provide credentials via `fly secrets set`.
- **AWS ECS** — Define `DB_*` as task-definition environment variables (or pull from Secrets Manager via `secrets:`). Set the task's healthcheck path to `/health`. The container binds 0.0.0.0:8000 by default, so the task definition's `containerPort` is `8000` unless `PORT` is overridden.
- **Google Cloud Run** — Set `PORT=8080` (Cloud Run's required port). Provide `DB_*` via Cloud Run environment variables or Secret Manager. For Cloud SQL, use the Cloud SQL Auth Proxy sidecar or the `--add-cloudsql-instances` flag and set `DB_HOST` to the proxy's socket path or IP.

---

## Notes

- All database credentials are injected via environment variables — no secrets in code.
- The API is stateless and read-only; horizontal scaling is safe.
- Database schema and data loading are managed by the upstream ETL service.
- Logging is structured to stdout so it integrates naturally with CloudWatch, Datadog, or any log aggregator.
