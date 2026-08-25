"""Tests for GET /health — component-level liveness and readiness check.

The endpoint reports the grocery and macro pipelines independently. The
grocery pipeline drives the overall status and HTTP code: 200 whenever it
can serve data (the macro database being unreachable only downgrades the
report to "degraded"), 503 only when the grocery pipeline itself cannot
serve data.
"""
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings

# --- overall status and HTTP code ----------------------------------------

def test_health_returns_200_when_both_pipelines_up(client):
    # Default client: bundled fixtures resolve (grocery up) and the mock
    # DB session does not raise (macro up).
    assert client.get("/health").status_code == 200


def test_health_status_healthy_when_both_pipelines_up(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_health_returns_200_when_macro_down_but_grocery_up(client, mock_db):
    mock_db.execute.side_effect = Exception("Connection refused")
    assert client.get("/health").status_code == 200


def test_health_status_degraded_when_macro_down_but_grocery_up(client, mock_db):
    mock_db.execute.side_effect = Exception("Connection refused")
    assert client.get("/health").json()["status"] == "degraded"


def test_health_returns_503_when_grocery_unavailable(client, tmp_path):
    # Point the fixtures directory at an empty directory and leave the
    # live *_PATH vars unset, so no grocery parquet resolves to a file.
    with patch.object(settings, "GROCERY_FIXTURES_DIR", str(tmp_path)):
        resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "unhealthy"


def test_health_unhealthy_when_grocery_down_even_if_macro_up(client, tmp_path):
    # Grocery being unavailable dominates the overall status: 503 even
    # though the mock DB session answers the macro probe.
    with patch.object(settings, "GROCERY_FIXTURES_DIR", str(tmp_path)):
        resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["macro_pipeline"]["status"] == "healthy"


# --- response shape ------------------------------------------------------

def test_health_response_has_version(client):
    assert "version" in client.get("/health").json()


def test_health_response_has_both_pipeline_sections(client):
    data = client.get("/health").json()
    assert "grocery_pipeline" in data
    assert "macro_pipeline" in data


def test_health_grocery_pipeline_reports_status_mode_and_path(client):
    grocery = client.get("/health").json()["grocery_pipeline"]
    assert grocery["status"] == "healthy"
    assert grocery["mode"] in ("online", "offline")
    assert "canonical_path" in grocery


# --- grocery pipeline mode -----------------------------------------------

def test_health_grocery_mode_is_offline_by_default(client):
    # No *_PATH env vars set in tests: the bundled fixtures are served.
    assert client.get("/health").json()["grocery_pipeline"]["mode"] == "offline"


def test_health_grocery_canonical_path_is_fixtures_dir_by_default(client):
    grocery = client.get("/health").json()["grocery_pipeline"]
    assert grocery["canonical_path"] == str(Path("app/fixtures"))


def test_health_grocery_mode_is_online_when_paths_exist(client, tmp_path):
    metrics = tmp_path / "store_daily_metrics.parquet"
    flags = tmp_path / "anomaly_flags.parquet"
    departments = tmp_path / "department_daily_metrics.parquet"
    dim_stores = tmp_path / "dim_stores.parquet"
    for parquet in (metrics, flags, departments, dim_stores):
        parquet.write_bytes(b"")
    with patch.object(settings, "STORE_METRICS_PATH", str(metrics)), \
         patch.object(settings, "ANOMALY_FLAGS_PATH", str(flags)), \
         patch.object(settings, "DEPARTMENT_METRICS_PATH", str(departments)), \
         patch.object(settings, "DIM_STORES_PATH", str(dim_stores)):
        grocery = client.get("/health").json()["grocery_pipeline"]
    assert grocery["mode"] == "online"
    assert grocery["canonical_path"] == str(tmp_path)


# --- macro pipeline ------------------------------------------------------

def test_health_macro_pipeline_healthy_when_db_reachable(client):
    # Default MagicMock.execute() does not raise — the DB is reachable.
    assert client.get("/health").json()["macro_pipeline"]["status"] == "healthy"


def test_health_macro_pipeline_unavailable_when_db_down(client, mock_db):
    mock_db.execute.side_effect = Exception("Connection refused")
    macro = client.get("/health").json()["macro_pipeline"]
    assert macro["status"] == "unavailable"
    assert "reason" in macro


def test_health_macro_pipeline_omits_reason_when_healthy(client):
    assert "reason" not in client.get("/health").json()["macro_pipeline"]


# --- log noise: the probe warning carries no traceback -------------------

def test_health_macro_db_failure_log_carries_no_traceback(client, mock_db):
    """Business-correctness: the macro DB probe warning, on a failed
    SELECT 1, must log the structured error and error_type fields but
    must not pass exc_info=True. Docker runs /health every 10s by default
    and the macro DB is intentionally unreachable in offline development
    and demo deployments; exc_info=True attached a ~30-line traceback to
    every probe warning. The trace adds no diagnostic value beyond the
    structured fields, so it was removed. This test pins that decision.
    """
    mock_db.execute.side_effect = Exception("Connection refused")

    with patch("app.main.logger") as mock_logger:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"

    probe_warnings = [
        call for call in mock_logger.warning.call_args_list
        if call.args and call.args[0] == "health_macro_db_check_failed"
    ]
    assert len(probe_warnings) == 1, "expected exactly one DB probe warning"

    kwargs = probe_warnings[0].kwargs
    assert "exc_info" not in kwargs
    assert kwargs["error"] == "Connection refused"
    assert kwargs["error_type"] == "Exception"
