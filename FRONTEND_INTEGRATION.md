# Frontend Integration Guide — Economic Data API

This document is the complete contract between the Economic Data API and any
frontend consuming it. Read this before writing a single line of UI code.

---

## 1. Connecting to the API

### Base URL

```
Development:  http://localhost:8000
Staging/Prod: set by deployment — store in an env var, never hardcode
```

Every endpoint path in this document is relative to the base URL.

### CORS

CORS is enabled on the API. During development the server allows all origins
(`*`). In staging and production the operator sets `CORS_ORIGINS` to a
comma-separated list of allowed frontend origins. If your frontend origin is
blocked, the API operator needs to add it to that env var — no frontend code
change required.

### HTTP method

Every endpoint is `GET`. The API is strictly read-only.

### Headers

No authentication headers are required at this time. No API key, no token.
This will be documented here if that changes.

```
Accept: application/json   ← optional, already the default
```

### Confirming connectivity

Before rendering anything, call `/health`. If it returns `503`, the database
is down and no data endpoints will work — show an appropriate error state.

```
GET /health
```

```json
{ "status": "ok", "version": "1.0.0", "db": "connected", "data_source": "fixtures" }
```

```json
{ "status": "degraded", "version": "1.0.0", "db": "unavailable", "data_source": "live" }
```

| Field | Values |
|---|---|
| `status` | `"ok"` or `"degraded"` |
| `db` | `"connected"` or `"unavailable"` |
| `data_source` | `"live"` or `"fixtures"` — see [section 8](#8-demo-mode) |
| HTTP status | `200` (ok) or `503` (degraded) |

`db` and `data_source` are independent signals. The HTTP status code reflects only the database probe; `data_source` is derived from filesystem checks and populates correctly even when the database is unavailable. The grocery endpoints (`/store-metrics`, `/anomalies`, `/dashboard-summary`) read from parquet rather than the database, so they continue to serve correctly during a `503`. Treat `db` as the gate for series/metrics/insights endpoints, and treat `data_source` as the gate for trusting grocery responses against live ETL output.

---

## 2. Data Conventions

These apply to every endpoint. Build your data layer around them once.

| Convention | Detail |
|---|---|
| Dates | ISO 8601 strings: `"2024-01-01"` — always `YYYY-MM-DD` |
| Numbers | JSON `number` (float). Never a string. May be `null` if the source reported no value for that period. |
| Nulls | Any `value`, `latest_value`, or `latest_date` field can be `null`. Always guard against this before rendering. |
| Sources | Currently `"FRED"` (Federal Reserve) and `"BLS"` (Bureau of Labor Statistics). **More sources will be added** — treat `source` as an opaque label, not an enum. |
| Series IDs | Opaque strings (e.g. `"CPIAUCSL"`, `"GDPC1"`). Use them as keys/identifiers. |
| Series names | Human-readable slugs (e.g. `"CPI_URBAN"`, `"GDP_REAL"`). These are ETL-generated labels, not end-user display strings — you may want to map them to friendlier labels in the UI. |

---

## 3. Error Responses

All errors return JSON. Build one central error handler for these shapes.

### Validation error — `422`

Triggered when a query parameter has the wrong type or fails a constraint
(e.g. `limit=0`, `start_date=not-a-date`).

```json
{
  "detail": [
    {
      "type": "greater_than",
      "loc": ["query", "limit"],
      "msg": "Input should be greater than 0",
      "input": "0"
    }
  ]
}
```

`detail` is always an array. Each item has `loc` (where the error is) and
`msg` (human-readable reason).

### Not found — `404`

```json
{ "detail": "Series 'NONEXISTENT' not found." }
```

`detail` is a string.

### Server error — `500`

```json
{ "detail": "An internal server error occurred." }
```

The API never leaks stack traces to the client.

### Database unavailable — `503`

Only returned by `/health`. All other endpoints will return `500` if the DB
goes down mid-request.

---

## 4. Endpoints

### 4.1 `GET /series` — List all series

Returns a paginated list of every available economic series.

**Query parameters**

| Param | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `limit` | integer | `50` | 1–200 | Items per page |
| `offset` | integer | `0` | ≥ 0 | Items to skip |

**Response `200`**

```json
{
  "total": 120,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "series_id": "CPIAUCSL",
      "series_name": "CPI_URBAN",
      "source": "BLS"
    },
    {
      "series_id": "GDPC1",
      "series_name": "GDP_REAL",
      "source": "FRED"
    }
  ]
}
```

**Pagination logic**

```
total_pages = ceil(total / limit)
has_next    = offset + limit < total
next_offset = offset + limit
```

The API does not return next/prev links — compute them from `total`, `limit`,
and `offset`.

---

### 4.2 `GET /series/{series_id}` — Single series with observations

Full observation history for one series. Use `start_date`/`end_date` to
limit the data returned — without filters this returns every observation
ever recorded, which may be hundreds of rows.

**Path parameters**

| Param | Description |
|---|---|
| `series_id` | Exact series identifier from the `/series` list |

**Query parameters**

| Param | Type | Description |
|---|---|---|
| `start_date` | `YYYY-MM-DD` | Include observations on or after this date |
| `end_date` | `YYYY-MM-DD` | Include observations on or before this date |

**Response `200`**

```json
{
  "series_id": "CPIAUCSL",
  "series_name": "CPI_URBAN",
  "source": "BLS",
  "observations": [
    { "observation_date": "2024-01-01", "value": 310.326 },
    { "observation_date": "2024-02-01", "value": 311.054 }
  ]
}
```

Observations are ordered chronologically (oldest first).

**Response `404`**

```json
{ "detail": "Series 'XYZ' not found." }
```

---

### 4.3 `GET /metrics/inflation` — Inflation series

Returns all inflation-related series. Each item includes the complete
observation history and a pre-computed `latest_date` / `latest_value` for
quick summary display without iterating observations.

**Query parameters** (all optional)

| Param | Type | Description |
|---|---|---|
| `start_date` | `YYYY-MM-DD` | Filter observations on or after this date |
| `end_date` | `YYYY-MM-DD` | Filter observations on or before this date |
| `series_id` | string | Return only this series |

**Response `200`**

```json
[
  {
    "series_id": "APU000074714",
    "series_name": "GAS_PRICE",
    "source": "BLS",
    "latest_date": "2026-02-01",
    "latest_value": 3.21,
    "observations": [
      { "observation_date": "2021-01-01", "value": 2.326 },
      { "observation_date": "2021-02-01", "value": 2.411 }
    ]
  }
]
```

`latest_date` and `latest_value` are derived from the observations array —
they always reflect the most recent observation in the (possibly filtered)
result. If `start_date`/`end_date` are used, `latest_date` reflects the
latest within that window, not the latest ever recorded.

---

### 4.4 `GET /metrics/unemployment` — Labor market series

Covers unemployment, wages, and employment indicators.
Same query parameters and response shape as `/metrics/inflation`.

```json
[
  {
    "series_id": "CES0500000003",
    "series_name": "AVG_WAGES",
    "source": "BLS",
    "latest_date": "2026-02-01",
    "latest_value": 37.32,
    "observations": [
      { "observation_date": "2021-01-01", "value": 29.93 }
    ]
  }
]
```

---

### 4.5 `GET /metrics/gdp` — GDP series

GDP and related output measures.
Same query parameters and response shape as `/metrics/inflation`.

```json
[
  {
    "series_id": "GDPC1",
    "series_name": "GDP_REAL",
    "source": "FRED",
    "latest_date": "2025-10-01",
    "latest_value": 24065.955,
    "observations": [
      { "observation_date": "2025-10-01", "value": 24065.955 }
    ]
  }
]
```

---

### 4.6 `GET /insights/summary` — Key indicators snapshot

Pre-aggregated latest value for every tracked series across all categories.
No query parameters. Ideal for a dashboard overview — one request, one
response, no pagination needed.

**Response `200`**

```json
{
  "indicators": [
    {
      "series_id": "CES0500000003",
      "series_name": "AVG_WAGES",
      "source": "BLS",
      "latest_date": "2026-02-01",
      "latest_value": 37.32
    },
    {
      "series_id": "GDPC1",
      "series_name": "GDP_REAL",
      "source": "FRED",
      "latest_date": "2025-10-01",
      "latest_value": 24065.955
    }
  ]
}
```

The `indicators` array may contain any number of entries and will grow as new
series are added to the pipeline. Do not hardcode the number of indicators or
assume a fixed order.

---

### 4.7 `GET /store-metrics` — Paginated store-day metrics

Rows from `store_daily_metrics` (one row per store per day) with date and store filters and pagination.

**Query parameters** (all optional)

| Param | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `start_date` | `YYYY-MM-DD` | — | — | Include rows on or after this date (inclusive) |
| `end_date` | `YYYY-MM-DD` | — | — | Include rows on or before this date (inclusive) |
| `store_id` | integer | — | 1–8 | Filter to a single store |
| `limit` | integer | `50` | 1–200 | Items per page |
| `offset` | integer | `0` | ≥ 0 | Items to skip |

**Response `200`**

```json
{
  "total": 1464,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "date": "2026-01-15",
      "store_id": 2,
      "total_sales": 121345.67,
      "transaction_count": 3198,
      "avg_basket_size": 37.94,
      "labor_cost_pct": 0.108
    }
  ]
}
```

`avg_basket_size` and `labor_cost_pct` may be `null` if the source row had no value.

---

### 4.8 `GET /anomalies` — Paginated anomaly flags

Rows from `anomaly_flags` (one row per detected exception) with date, store, severity, and rule filters.

**Query parameters** (all optional)

| Param | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `start_date` | `YYYY-MM-DD` | — | — | Include rows on or after this date |
| `end_date` | `YYYY-MM-DD` | — | — | Include rows on or before this date |
| `store_id` | integer | — | 1–8 | Filter to a single store |
| `severity_level` | string | — | `info` / `warning` / `critical` | Filter to a severity level. Unknown values return 422. |
| `rule_id` | string | — | `revenue_band` / `labor_pct_band` / `transactions_band` | Filter to a detection rule. Unknown values return 422. |
| `limit` | integer | `50` | 1–200 | Items per page |
| `offset` | integer | `0` | ≥ 0 | Items to skip |

**Response `200`**

```json
{
  "total": 45,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "date": "2026-01-15",
      "store_id": 2,
      "rule_id": "revenue_band",
      "actual_value": 145000.0,
      "expected_low": 78000.0,
      "expected_high": 125000.0,
      "distance_from_band": 20000.0,
      "severity_score": 0.87,
      "severity_level": "info"
    }
  ]
}
```

`severity_score` is a unitless ratio of how far the actual value sits beyond the expected band, expressed in band-widths. Use `severity_level` for display bucketing rather than thresholding `severity_score` yourself — the bucket boundaries may shift in future detection releases.

---

### 4.9 `GET /dashboard-summary` — Composed KPI overview

Single request that returns aggregated totals, top stores by revenue, exception counts by severity, and a daily sales trend over a required date window. Designed for the portal's overview page so it renders with one round-trip.

**Query parameters** (both required)

| Param | Type | Description |
|---|---|---|
| `start_date` | `YYYY-MM-DD` | Start of the summary window (inclusive) |
| `end_date` | `YYYY-MM-DD` | End of the summary window (inclusive) |

**Responses**

| Status | Condition |
|---|---|
| `200` | Summary returned |
| `400` | `start_date` is after `end_date` (clear `detail` message) |
| `422` | Either date is missing or malformed |

**Response `200`**

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-01-31",
  "total_sales": 18546721.42,
  "total_transactions": 487234,
  "average_labor_cost_pct": 0.1124,
  "top_stores_by_revenue": [
    { "store_id": 2, "total_sales": 3320145.10 },
    { "store_id": 1, "total_sales": 2890432.55 },
    { "store_id": 3, "total_sales": 2410988.30 },
    { "store_id": 4, "total_sales": 1985441.05 },
    { "store_id": 6, "total_sales": 1820772.18 }
  ],
  "exception_count_by_severity": [
    { "severity_level": "info",     "count": 14 },
    { "severity_level": "warning",  "count": 4 },
    { "severity_level": "critical", "count": 1 }
  ],
  "daily_sales_trend": [
    { "date": "2026-01-01", "total_sales": 612043.21, "transaction_count": 16002 },
    { "date": "2026-01-02", "total_sales": 598320.55, "transaction_count": 15741 }
  ]
}
```

`top_stores_by_revenue` is capped at five entries, sorted descending. `exception_count_by_severity` always contains all three severity levels, even when one or more counts are zero — render the buckets unconditionally rather than hiding empty ones. `daily_sales_trend` contains exactly one entry per date in the window where any store had sales; missing days indicate no data, not zero sales.

---

## 5. Recommended Request Patterns

### Dashboard overview page

```
GET /health                  → check connectivity first
GET /insights/summary        → render all latest values in one shot
```

### Chart / detail page for a specific metric

```
GET /metrics/gdp?start_date=2020-01-01
GET /metrics/inflation?series_id=CPIAUCSL&start_date=2020-01-01
```

### Series explorer / search page

```
GET /series?limit=50&offset=0   → paginate the catalogue
GET /series/{series_id}?start_date=2018-01-01   → load chart data on select
```

---

## 6. What Will Change — Build for Growth

The API is at MVP. The following will expand over time. Build defensively
around these areas.

### New data sources

`source` is currently `"FRED"` or `"BLS"`. Additional sources will be added
(e.g. World Bank, Census Bureau, ECB). Always render `source` dynamically —
never branch on its value for display logic.

### New series

The `/series` endpoint `total` will grow. The `/insights/summary` indicators
array will grow. Do not assume fixed counts or fixed `series_id` values.

### New metric categories

Additional `GET /metrics/{category}` endpoints may be added (e.g.
`/metrics/housing`, `/metrics/trade`). The response shape will be identical
to the existing metric endpoints. Design your data-fetching layer so adding a
new category requires only a new URL, not a new code path.

### Response shape additions

Fields may be added to responses in a non-breaking way (new optional keys).
Use flexible deserialization — ignore unknown fields rather than erroring on
them.

### Planned: `/contextual-insights`

A future endpoint will join macroeconomic context (CPI, unemployment) onto
Knot Shore performance — surfacing narratives like "exception rate during
periods of elevated unemployment." Originally scoped for this release and
deferred pending portal-side requirement clarification on which insights
are actually useful in the dashboard. Build the data layer with this in
mind but do not depend on it yet.

---

## 7. Interactive Documentation

While the API is running, full interactive docs are available:

- **Swagger UI** (try every endpoint live): `http://localhost:8000/docs`
- **ReDoc** (clean reference format): `http://localhost:8000/redoc`

These are auto-generated from the code and always reflect the actual current
API — use them to verify request/response shapes during development.

---

## 8. Demo Mode

The API ships with a bundled demo dataset so it works out of the box on a
fresh clone. The grocery endpoints (`/store-metrics`, `/anomalies`,
`/dashboard-summary`) auto-detect their data source on every request:

- **Live mode** — the operator has set `STORE_METRICS_PATH` and
  `ANOMALY_FLAGS_PATH` to readable parquet files (typically the upstream
  ETL's `data/processed/` output). The API serves real data.
- **Demo mode** — those env vars are unset or unreadable. The API falls
  back to bundled fixture parquets in `app/fixtures/`, logs a startup
  WARNING, and reports `data_source: "fixtures"` on `/health`.

The `data_source` field on `/health` is the authoritative signal of which
mode is active. From a frontend perspective the JSON shape is identical in
both modes — there is nothing the UI needs to switch on. The flag exists for
operators debugging an unexpected `/health` payload, and as a safety check
when verifying a deployment ("am I really pointing at the live ETL?").

**The demo dataset is real pipeline output.** It is a byte-identical
snapshot of a 184-day canonical run of the upstream sim engine + ETL
pipeline (2025-07-01 through 2025-12-31, eight Knot Shore-style stores).
The sim engine generates synthetic store-day data, the ETL ingests it
and runs anomaly detection, and the resulting parquets are committed to
this repo as the bundled fixtures. Treat these values as representative
of the response shape and dynamic range your UI must handle, but not as
production reference for any business decision — the underlying
operational data is itself synthetic.

Switching to live data is purely an operator concern: set the two env vars
and restart the API. No frontend code change is required.
