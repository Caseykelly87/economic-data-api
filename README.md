# Economic Data API

A read-only REST API that exposes economic time-series data stored in PostgreSQL. Built with FastAPI and SQLAlchemy, designed as the query layer of a multi-service data platform. The upstream ETL pipeline owns all data ingestion and schema management — this service only reads.

## Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12+ |
| Web framework | FastAPI |
| ORM | SQLAlchemy 2.0 (read-only) |
| Validation | Pydantic v2 |
| Database | PostgreSQL (AWS RDS) |
| Testing | Pytest + httpx |

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
| `DB_HOST` | Yes | — | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_NAME` | Yes | — | Database name |
| `DB_USER` | Yes | — | Database user |
| `DB_PASSWORD` | Yes | — | Database password |
| `API_ENV` | No | `development` | Environment label |
| `API_TITLE` | No | `Economic Data API` | Title shown in docs |
| `API_VERSION` | No | `1.0.0` | Version shown in docs |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `LOG_FORMAT` | No | auto | `console` (colored text) or `json`. Auto-detects: console when stdout is a tty, json when piped or redirected. |
| `STORE_METRICS_PATH` | No | — | Path to live `store_daily_metrics.parquet` from the upstream ETL. Falls back to bundled fixtures if unset or unreadable. |
| `ANOMALY_FLAGS_PATH` | No | — | Path to live `anomaly_flags.parquet` from the upstream ETL. Falls back to bundled fixtures if unset or unreadable. |
| `GROCERY_FIXTURES_DIR` | No | `app/fixtures` | Directory where bundled demo parquets live. Used as the fallback source. |

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

The API emits structured logs via [structlog](https://www.structlog.org/).
Output is human-readable colored text when stdout is a tty, single-line
JSON otherwise. Format and verbosity can be controlled via environment
variables:

| Variable | Values | Default |
|---|---|---|
| `LOG_LEVEL` | `debug`, `info`, `warning`, `error`, `critical` | `info` |
| `LOG_FORMAT` | `console`, `json` | auto (console if tty, else json) |

### Request correlation

Every inbound HTTP request is tagged with a UUID. The middleware:

- Generates a UUID per request, OR uses the value of the incoming
  `X-Request-ID` header if the caller provides one.
- Binds the ID to structlog's contextvars so every log line emitted
  during the request lifetime includes a `request_id` field.
- Echoes the ID on the response's `X-Request-ID` header so callers
  can correlate from their side.

Example: when the portal calls `/store-metrics`, it can pass
`X-Request-ID: <its-own-id>` and the API's logs for that request will
show the same `request_id`, making it possible to trace one user's
flow across portal logs and API logs by grepping for one UUID.

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

The API exposes a `/metrics` endpoint in Prometheus text format. Any
Prometheus-compatible scraper can poll this endpoint to collect
time-series data on request rates, latencies, and custom counters.

```bash
curl http://localhost:8000/metrics
```

### Auto-instrumented HTTP metrics

The [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)
library produces three standard metrics for every route:

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | Counter | `method`, `handler`, `status` |
| `http_request_duration_seconds` | Histogram | `method`, `handler` |
| `http_requests_inprogress` | Gauge | `method`, `handler` |

### Custom counters

Two custom counters track operational facts specific to the grocery
endpoints:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `grocery_data_source_total` | Counter | `source` | Increments per grocery request. `source` is `fixtures` or `live` based on `STORE_METRICS_PATH` and `ANOMALY_FLAGS_PATH` configuration. |
| `service_call_total` | Counter | `service` | Increments per grocery service-layer call. `service` is one of `get_store_metrics`, `get_anomalies`, `get_dashboard_summary`. |

Both counters increment at the same call sites as the corresponding
structured log events (`service_call_started` and
`service_call_completed`). Logs give per-call detail; metrics give
aggregate rates.

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

The `/metrics` endpoint is unauthenticated. Production deployments
should restrict access via firewall rules, an authenticating reverse
proxy, or a service mesh — Prometheus convention is metrics endpoints
sit inside trusted networks.

---

## Testing

Tests mock the service layer and do not require a database connection.

```bash
pytest
pytest -v          # verbose
pytest tests/test_metrics.py   # single file
```

---

## Endpoints

### Health

#### `GET /health`

Liveness and readiness check. Pings the database with `SELECT 1`.

**Responses**

| Status | Condition |
|---|---|
| `200` | API and database are both reachable |
| `503` | Database is unreachable |

```json
{ "status": "ok", "version": "1.0.0", "db": "connected", "data_source": "fixtures" }
```

```json
{ "status": "degraded", "version": "1.0.0", "db": "unavailable", "data_source": "live" }
```

`data_source` reports which grocery dataset the API is serving — `"live"` when `STORE_METRICS_PATH` and `ANOMALY_FLAGS_PATH` both point at readable parquet files, `"fixtures"` when the API has fallen back to the bundled demo dataset.

The `db` and `data_source` fields are independent. `data_source` is computed from filesystem checks and populates correctly regardless of database availability, so a `503` response with `data_source: "fixtures"` still carries valid grocery-data signaling. In environments without a reachable PostgreSQL instance — local sandboxes, throwaway containers — `/health` will return `503` while the grocery endpoints (`/store-metrics`, `/anomalies`, `/dashboard-summary`) continue to serve correctly, since they read from parquet rather than the database.

---

### Series

#### `GET /series`

List all available economic series with pagination.

**Query parameters**

| Param | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `limit` | int | `50` | 1–200 | Number of results to return |
| `offset` | int | `0` | ≥ 0 | Number of results to skip |

**Response** `200`

```json
{
  "total": 120,
  "limit": 50,
  "offset": 0,
  "items": [
    { "series_id": "CPIAUCSL", "series_name": "CPI_URBAN", "source": "BLS" }
  ]
}
```

---

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

### Metrics

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

### Grocery Data Endpoints

Three endpoints expose the upstream ETL's parquet outputs (`store_daily_metrics`, `anomaly_flags`) as JSON. They power the Knot Shore portal's KPI overview, exception list, and store-detail views.

#### `GET /store-metrics`

Paginated store-day metric rows. Filterable by `start_date`, `end_date`, `store_id`. Pagination via `limit` (1–200, default 50) and `offset`. Same envelope as `/series` (`total`, `limit`, `offset`, `items`).

#### `GET /anomalies`

Paginated detection flags. Filterable by `start_date`, `end_date`, `store_id`, `severity_level` (`info`/`warning`/`critical`), and `rule_id` (`revenue_band`/`labor_pct_band`/`transactions_band`). Same envelope.

#### `GET /dashboard-summary`

Single-shot KPI overview over a required `start_date`/`end_date` window: total sales, total transactions, average labor pct, top-5 stores by revenue, exception counts by severity (always all three levels reported, including zero counts), and a daily sales trend series.

#### Live mode vs demo mode

The API runs in one of two modes, automatically detected at request time:

- **Live** — `STORE_METRICS_PATH` and `ANOMALY_FLAGS_PATH` env vars both point at readable parquet files (typically the ETL's `data/processed/` output). `/health` reports `data_source: "live"`.
- **Demo** — the env vars are unset or point at unreadable paths. The API serves the bundled fixture parquets at `app/fixtures/`. The startup log prints a WARNING and `/health` reports `data_source: "fixtures"`.

Demo mode is the default for fresh clones — the API works out of the box without any configuration.

#### Refreshing bundled demo fixtures

The fixtures in `app/fixtures/` (`store_daily_metrics.parquet` and `anomaly_flags.parquet`) are byte-identical copies of the canonical pipeline output committed at `data/processed/canonical/` in the upstream `economic-data-etl` repository. They are produced by running the actual sim engine and ETL pipeline end-to-end against the canonical 184-day backfill window — they are not separately generated synthetic data.

Current canonical contents:

- `store_daily_metrics.parquet` — 1,472 rows × 6 columns; 8 stores × 184 days from 2025-07-01 through 2025-12-31
- `anomaly_flags.parquet` — 453 rows × 9 columns; 438 info-severity, 15 warning-severity, 0 critical-severity

To refresh: regenerate the canonical parquets in the upstream ETL repo (`scripts/build_canonical_fixtures.py` there), then copy the resulting files into this repo's `app/fixtures/` and commit. The upstream pipeline is byte-deterministic, so successive regenerations against the same window produce identical bytes.

#### Planned: `GET /contextual-insights`

Originally scoped for this MVP and deferred pending portal-side requirement clarification. Will join macroeconomic context (CPI, unemployment) onto Knot Shore performance to surface "exceptions during economic stress" narratives.

---

## Architecture

```
app/
├── main.py                  # App factory, middleware, health route, error handler
├── core/
│   ├── config.py            # Settings loaded from environment / .env
│   └── logging_config.py    # Logging setup (called once at startup)
├── api/routes/
│   ├── series.py            # /series endpoints
│   ├── metrics.py           # /metrics endpoints
│   ├── insights.py          # /insights endpoints
│   ├── store_metrics.py     # /store-metrics endpoint
│   ├── anomalies.py         # /anomalies endpoint
│   └── dashboard.py         # /dashboard-summary endpoint
├── fixtures/                # Bundled demo parquets (copies of upstream ETL canonical output)
├── models/economic.py       # SQLAlchemy ORM models (read-only, no migrations)
├── schemas/
│   ├── economic.py          # Pydantic schemas for series/metrics/insights
│   └── grocery.py           # Pydantic schemas for grocery endpoints
└── services/
    ├── economic.py          # Query logic for postgres-backed endpoints
    └── grocery.py           # Parquet IO + aggregation for grocery endpoints

scripts/
└── inspect_schema.py          # Ad-hoc DB schema inspection helper

tests/
├── conftest.py              # Client fixture with mocked DB session
├── test_health.py
├── test_series.py
├── test_metrics.py
├── test_insights.py
├── test_grocery_service.py
├── test_store_metrics.py
├── test_anomalies.py
└── test_dashboard.py
```

### Database schemas

| Schema | Purpose |
|---|---|
| `raw` | Source-of-truth tables populated by the ETL pipeline |
| `public_analytics` | Pre-aggregated mart tables optimised for API reads |

This API reads from both schemas but never writes. Adding a new data source means updating the ETL pipeline; the API automatically surfaces the new data through the existing endpoints.

---

## Notes

- All database credentials are injected via environment variables — no secrets in code.
- The API is stateless and read-only; horizontal scaling is safe.
- Database schema and data loading are managed by the upstream ETL service.
- Logging is structured to stdout so it integrates naturally with CloudWatch, Datadog, or any log aggregator.
