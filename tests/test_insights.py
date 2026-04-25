"""
Tests for GET /insights/summary.

Service functions are patched so tests are isolated from the DB.
"""
from datetime import date
from unittest.mock import patch

from app.schemas.economic import KeyIndicator, SummaryOut

SVC = "app.services.economic"


def _indicator(**kwargs) -> KeyIndicator:
    defaults = dict(
        series_id="CPIAUCSL", series_name="Consumer Price Index", source="BLS",
        latest_date=date(2024, 6, 1), latest_value=3.5,
    )
    return KeyIndicator(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# GET /insights/summary
# ---------------------------------------------------------------------------

def test_summary_returns_200(client):
    with patch(f"{SVC}.get_summary", return_value=SummaryOut(indicators=[])):
        resp = client.get("/insights/summary")
    assert resp.status_code == 200


def test_summary_has_indicators_key(client):
    with patch(f"{SVC}.get_summary", return_value=SummaryOut(indicators=[])):
        resp = client.get("/insights/summary")
    data = resp.json()
    assert "indicators" in data
    assert isinstance(data["indicators"], list)


def test_summary_indicator_shape(client):
    with patch(f"{SVC}.get_summary", return_value=SummaryOut(indicators=[_indicator()])):
        resp = client.get("/insights/summary")
    item = resp.json()["indicators"][0]
    for field in ("series_id", "series_name", "source", "latest_date", "latest_value"):
        assert field in item, f"Missing field: {field}"


def test_summary_values_correct(client):
    ind = _indicator(latest_date=date(2024, 6, 1), latest_value=3.5)
    with patch(f"{SVC}.get_summary", return_value=SummaryOut(indicators=[ind])):
        resp = client.get("/insights/summary")
    item = resp.json()["indicators"][0]
    assert item["latest_date"] == "2024-06-01"
    assert float(item["latest_value"]) == 3.5
