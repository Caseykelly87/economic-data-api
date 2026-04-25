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
{ "status": "ok", "version": "1.0.0", "db": "connected" }
```

```json
{ "status": "degraded", "version": "1.0.0", "db": "unavailable" }
```

| Field | Values |
|---|---|
| `status` | `"ok"` or `"degraded"` |
| `db` | `"connected"` or `"unavailable"` |
| HTTP status | `200` (ok) or `503` (degraded) |

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

---

## 7. Interactive Documentation

While the API is running, full interactive docs are available:

- **Swagger UI** (try every endpoint live): `http://localhost:8000/docs`
- **ReDoc** (clean reference format): `http://localhost:8000/redoc`

These are auto-generated from the code and always reflect the actual current
API — use them to verify request/response shapes during development.
