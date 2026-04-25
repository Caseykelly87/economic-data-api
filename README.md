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
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## Running

```bash
uvicorn app.main:app --reload
```

- API: `http://localhost:8000`
- Interactive docs (Swagger UI): `http://localhost:8000/docs`
- Alternative docs (ReDoc): `http://localhost:8000/redoc`

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
{ "status": "ok", "version": "1.0.0", "db": "connected" }
```

```json
{ "status": "degraded", "version": "1.0.0", "db": "unavailable" }
```

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
│   └── insights.py          # /insights endpoints
├── models/economic.py       # SQLAlchemy ORM models (read-only, no migrations)
├── schemas/economic.py      # Pydantic request/response schemas
└── services/economic.py     # Query logic; all DB access lives here

tests/
├── conftest.py              # Client fixture with mocked DB session
├── test_health.py
├── test_series.py
├── test_metrics.py
└── test_insights.py
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
