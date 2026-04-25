"""Tests for GET /anomalies.

Service is patched so tests are isolated from parquet io.
"""
from datetime import date
from unittest.mock import patch

from app.schemas.grocery import AnomalyFlagOut

SVC = "app.services.grocery"

REQUIRED_ITEM_FIELDS = (
    "date", "store_id", "rule_id", "actual_value",
    "expected_low", "expected_high", "distance_from_band",
    "severity_score", "severity_level",
)
ENVELOPE_FIELDS = ("total", "limit", "offset", "items")


def _flag(**kwargs) -> AnomalyFlagOut:
    defaults = dict(
        date=date(2026, 1, 15),
        store_id=2,
        rule_id="revenue_band",
        actual_value=145000.0,
        expected_low=78000.0,
        expected_high=125000.0,
        distance_from_band=20000.0,
        severity_score=0.42,
        severity_level="info",
    )
    return AnomalyFlagOut(**{**defaults, **kwargs})


def test_anomalies_returns_200_empty(client):
    with patch(f"{SVC}.get_anomalies", return_value=(0, [])):
        resp = client.get("/anomalies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_anomalies_envelope_shape(client):
    with patch(f"{SVC}.get_anomalies", return_value=(1, [_flag()])):
        resp = client.get("/anomalies")
    body = resp.json()
    for f in ENVELOPE_FIELDS:
        assert f in body, f"Missing envelope field: {f}"


def test_anomalies_item_shape(client):
    with patch(f"{SVC}.get_anomalies", return_value=(1, [_flag()])):
        resp = client.get("/anomalies")
    item = resp.json()["items"][0]
    for f in REQUIRED_ITEM_FIELDS:
        assert f in item, f"Missing item field: {f}"


def test_anomalies_date_filters_forwarded(client):
    with patch(f"{SVC}.get_anomalies", return_value=(0, [])) as mock:
        client.get("/anomalies?start_date=2026-01-01&end_date=2026-01-31")
    _, kwargs = mock.call_args
    assert kwargs["start_date"] == date(2026, 1, 1)
    assert kwargs["end_date"] == date(2026, 1, 31)


def test_anomalies_store_id_filter_forwarded(client):
    with patch(f"{SVC}.get_anomalies", return_value=(0, [])) as mock:
        client.get("/anomalies?store_id=4")
    _, kwargs = mock.call_args
    assert kwargs["store_id"] == 4


def test_anomalies_severity_filter_forwarded(client):
    with patch(f"{SVC}.get_anomalies", return_value=(0, [])) as mock:
        client.get("/anomalies?severity_level=critical")
    _, kwargs = mock.call_args
    assert kwargs["severity_level"] == "critical"


def test_anomalies_rule_filter_forwarded(client):
    with patch(f"{SVC}.get_anomalies", return_value=(0, [])) as mock:
        client.get("/anomalies?rule_id=revenue_band")
    _, kwargs = mock.call_args
    assert kwargs["rule_id"] == "revenue_band"


def test_anomalies_limit_offset_forwarded(client):
    with patch(f"{SVC}.get_anomalies", return_value=(0, [])) as mock:
        client.get("/anomalies?limit=10&offset=20")
    _, kwargs = mock.call_args
    assert kwargs["limit"] == 10
    assert kwargs["offset"] == 20


def test_anomalies_invalid_severity_returns_422(client):
    resp = client.get("/anomalies?severity_level=catastrophic")
    assert resp.status_code == 422


def test_anomalies_invalid_rule_returns_422(client):
    resp = client.get("/anomalies?rule_id=bogus_rule")
    assert resp.status_code == 422


def test_anomalies_limit_zero_returns_422(client):
    resp = client.get("/anomalies?limit=0")
    assert resp.status_code == 422


def test_anomalies_limit_too_large_returns_422(client):
    resp = client.get("/anomalies?limit=300")
    assert resp.status_code == 422


def test_anomalies_invalid_date_returns_422(client):
    resp = client.get("/anomalies?start_date=not-a-date")
    assert resp.status_code == 422
