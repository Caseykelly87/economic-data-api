# Economic Data API

A production-grade, read-only REST API that exposes economic data stored in PostgreSQL. Built with FastAPI and SQLAlchemy, designed for integration into a containerized multi-service data platform.

## Stack

- Python 3.12+
- FastAPI
- SQLAlchemy 2.0 (ORM, read-only)
- Pydantic v2
- PostgreSQL (AWS RDS)
- Pytest

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your database credentials
```

## Running

```bash
uvicorn app.main:app --reload
```

## Testing

```bash
pytest
```

## Endpoints

| Method | Path                   | Description                          |
|--------|------------------------|--------------------------------------|
| GET    | /health                | Service health check                 |
| GET    | /series                | List available economic series       |
| GET    | /series/{series_id}    | Data for a specific series           |
| GET    | /metrics/inflation     | Inflation-related data               |
| GET    | /metrics/unemployment  | Unemployment-related data            |
| GET    | /insights/summary      | Aggregated summary of key indicators |

## Notes

- This API is strictly read-only. No write operations are performed.
- All database credentials are loaded from environment variables.
- Database schema is managed by the upstream ETL service.
