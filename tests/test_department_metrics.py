"""Tests for GET /department-metrics.

Service is patched so tests are isolated from parquet io.
"""
from datetime import date
from unittest.mock import patch

from app.schemas.grocery import DepartmentMetricOut

SVC = "app.services.grocery"

REQUIRED_ITEM_FIELDS = (
    "date", "store_id", "department_id",
    "net_sales", "transactions", "units_sold", "gross_margin_pct",
)
ENVELOPE_FIELDS = ("total", "limit", "offset", "items")


def _row(**kwargs) -> DepartmentMetricOut:
    defaults = dict(
        date=date(2025, 7, 1),
        store_id=1,
        department_id=1,
        net_sales=10639.13,
        transactions=288,
        units_sold=928,
        gross_margin_pct=0.48,
    )
    return DepartmentMetricOut(**{**defaults, **kwargs})


def test_department_metrics_returns_200_empty(client):
    with patch(f"{SVC}.get_department_metrics", return_value=(0, [])):
        resp = client.get("/department-metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_department_metrics_envelope_shape(client):
    with patch(f"{SVC}.get_department_metrics", return_value=(1, [_row()])):
        resp = client.get("/department-metrics")
    assert resp.status_code == 200
    body = resp.json()
    for field in ENVELOPE_FIELDS:
        assert field in body, f"missing envelope field: {field}"


def test_department_metrics_item_shape(client):
    with patch(f"{SVC}.get_department_metrics", return_value=(1, [_row()])):
        resp = client.get("/department-metrics")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    for field in REQUIRED_ITEM_FIELDS:
        assert field in item, f"missing item field: {field}"


def test_department_metrics_default_pagination(client):
    with patch(f"{SVC}.get_department_metrics", return_value=(0, [])) as m:
        resp = client.get("/department-metrics")
    assert resp.status_code == 200
    kwargs = m.call_args.kwargs
    assert kwargs["limit"] == 50
    assert kwargs["offset"] == 0


def test_department_metrics_passes_filters_to_service(client):
    with patch(f"{SVC}.get_department_metrics", return_value=(0, [])) as m:
        resp = client.get(
            "/department-metrics",
            params={
                "start_date": "2025-07-01",
                "end_date": "2025-07-31",
                "store_id": 3,
                "department_id": 5,
                "limit": 25,
                "offset": 10,
            },
        )
    assert resp.status_code == 200
    kwargs = m.call_args.kwargs
    assert kwargs["start_date"] == date(2025, 7, 1)
    assert kwargs["end_date"] == date(2025, 7, 31)
    assert kwargs["store_id"] == 3
    assert kwargs["department_id"] == 5
    assert kwargs["limit"] == 25
    assert kwargs["offset"] == 10


def test_department_metrics_rejects_store_id_out_of_range(client):
    resp = client.get("/department-metrics", params={"store_id": 99})
    assert resp.status_code == 422


def test_department_metrics_rejects_department_id_out_of_range(client):
    resp = client.get("/department-metrics", params={"department_id": 99})
    assert resp.status_code == 422


def test_department_metrics_rejects_negative_offset(client):
    resp = client.get("/department-metrics", params={"offset": -1})
    assert resp.status_code == 422


def test_department_metrics_rejects_limit_above_max(client):
    resp = client.get("/department-metrics", params={"limit": 999})
    assert resp.status_code == 422
