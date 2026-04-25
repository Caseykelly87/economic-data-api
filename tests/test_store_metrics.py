"""Tests for GET /store-metrics.

Service is patched so tests are isolated from parquet io.
"""
from datetime import date
from unittest.mock import patch

from app.schemas.grocery import StoreMetricOut

SVC = "app.services.grocery"

REQUIRED_ITEM_FIELDS = (
    "date", "store_id", "total_sales", "transaction_count",
    "avg_basket_size", "labor_cost_pct",
)
ENVELOPE_FIELDS = ("total", "limit", "offset", "items")


def _row(**kwargs) -> StoreMetricOut:
    defaults = dict(
        date=date(2026, 1, 15),
        store_id=1,
        total_sales=98765.43,
        transaction_count=2300,
        avg_basket_size=42.94,
        labor_cost_pct=0.108,
    )
    return StoreMetricOut(**{**defaults, **kwargs})


def test_store_metrics_returns_200_empty(client):
    with patch(f"{SVC}.get_store_metrics", return_value=(0, [])):
        resp = client.get("/store-metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_store_metrics_envelope_shape(client):
    with patch(f"{SVC}.get_store_metrics", return_value=(1, [_row()])):
        resp = client.get("/store-metrics")
    body = resp.json()
    for f in ENVELOPE_FIELDS:
        assert f in body, f"Missing envelope field: {f}"


def test_store_metrics_item_shape(client):
    with patch(f"{SVC}.get_store_metrics", return_value=(1, [_row()])):
        resp = client.get("/store-metrics")
    item = resp.json()["items"][0]
    for f in REQUIRED_ITEM_FIELDS:
        assert f in item, f"Missing item field: {f}"


def test_store_metrics_date_filters_forwarded(client):
    with patch(f"{SVC}.get_store_metrics", return_value=(0, [])) as mock:
        client.get("/store-metrics?start_date=2026-01-01&end_date=2026-01-31")
    _, kwargs = mock.call_args
    assert kwargs["start_date"] == date(2026, 1, 1)
    assert kwargs["end_date"] == date(2026, 1, 31)


def test_store_metrics_store_id_filter_forwarded(client):
    with patch(f"{SVC}.get_store_metrics", return_value=(0, [])) as mock:
        client.get("/store-metrics?store_id=3")
    _, kwargs = mock.call_args
    assert kwargs["store_id"] == 3


def test_store_metrics_limit_offset_forwarded(client):
    with patch(f"{SVC}.get_store_metrics", return_value=(0, [])) as mock:
        client.get("/store-metrics?limit=25&offset=50")
    _, kwargs = mock.call_args
    assert kwargs["limit"] == 25
    assert kwargs["offset"] == 50


def test_store_metrics_limit_zero_returns_422(client):
    resp = client.get("/store-metrics?limit=0")
    assert resp.status_code == 422


def test_store_metrics_limit_too_large_returns_422(client):
    resp = client.get("/store-metrics?limit=300")
    assert resp.status_code == 422


def test_store_metrics_invalid_date_returns_422(client):
    resp = client.get("/store-metrics?start_date=not-a-date")
    assert resp.status_code == 422


def test_store_metrics_negative_offset_returns_422(client):
    resp = client.get("/store-metrics?offset=-1")
    assert resp.status_code == 422
