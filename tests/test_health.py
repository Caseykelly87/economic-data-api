"""Tests for GET /health — status check including DB connectivity."""
from unittest.mock import patch


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_has_status_ok(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"


def test_health_response_has_version(client):
    data = client.get("/health").json()
    assert "version" in data


def test_health_response_has_db_field(client):
    data = client.get("/health").json()
    assert "db" in data


def test_health_db_connected_when_ping_succeeds(client):
    # Default MagicMock.execute() does not raise — DB is reachable.
    data = client.get("/health").json()
    assert data["db"] == "connected"


def test_health_returns_503_when_db_unavailable(client, mock_db):
    mock_db.execute.side_effect = Exception("Connection refused")
    resp = client.get("/health")
    assert resp.status_code == 503


def test_health_status_degraded_when_db_unavailable(client, mock_db):
    mock_db.execute.side_effect = Exception("Connection refused")
    data = client.get("/health").json()
    assert data["status"] == "degraded"
    assert data["db"] == "unavailable"


def test_health_response_has_data_source_field(client):
    data = client.get("/health").json()
    assert "data_source" in data


def test_health_data_source_is_fixtures_by_default(client):
    # No STORE_METRICS_PATH or ANOMALY_FLAGS_PATH env var set in tests.
    data = client.get("/health").json()
    assert data["data_source"] == "fixtures"


def test_health_data_source_is_live_when_paths_exist(client, tmp_path):
    metrics = tmp_path / "store_daily_metrics.parquet"
    flags = tmp_path / "anomaly_flags.parquet"
    departments = tmp_path / "department_daily_metrics.parquet"
    dim_stores = tmp_path / "dim_stores.parquet"
    metrics.write_bytes(b"")
    flags.write_bytes(b"")
    departments.write_bytes(b"")
    dim_stores.write_bytes(b"")
    from app.core.config import settings
    with patch.object(settings, "STORE_METRICS_PATH", str(metrics)), \
         patch.object(settings, "ANOMALY_FLAGS_PATH", str(flags)), \
         patch.object(settings, "DEPARTMENT_METRICS_PATH", str(departments)), \
         patch.object(settings, "DIM_STORES_PATH", str(dim_stores)):
        data = client.get("/health").json()
    assert data["data_source"] == "live"
