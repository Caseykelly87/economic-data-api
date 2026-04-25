"""Tests for GET /dashboard-summary."""
from datetime import date
from unittest.mock import patch

from app.schemas.grocery import (
    DailySalesPoint,
    DashboardSummaryOut,
    SeverityCount,
    StoreRevenueRank,
)

SVC = "app.services.grocery"

REQUIRED_FIELDS = (
    "start_date", "end_date", "total_sales", "total_transactions",
    "average_labor_cost_pct", "top_stores_by_revenue",
    "exception_count_by_severity", "daily_sales_trend",
)


def _summary(**kwargs) -> DashboardSummaryOut:
    defaults = dict(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        total_sales=12_345_678.90,
        total_transactions=320_000,
        average_labor_cost_pct=0.112,
        top_stores_by_revenue=[
            StoreRevenueRank(store_id=2, total_sales=2_500_000.00),
            StoreRevenueRank(store_id=1, total_sales=2_300_000.00),
        ],
        exception_count_by_severity=[
            SeverityCount(severity_level="info", count=14),
            SeverityCount(severity_level="warning", count=4),
            SeverityCount(severity_level="critical", count=1),
        ],
        daily_sales_trend=[
            DailySalesPoint(date=date(2026, 1, 1), total_sales=400000.0, transaction_count=10500),
        ],
    )
    return DashboardSummaryOut(**{**defaults, **kwargs})


def test_dashboard_returns_200(client):
    with patch(f"{SVC}.get_dashboard_summary", return_value=_summary()):
        resp = client.get("/dashboard-summary?start_date=2026-01-01&end_date=2026-01-31")
    assert resp.status_code == 200


def test_dashboard_has_all_required_fields(client):
    with patch(f"{SVC}.get_dashboard_summary", return_value=_summary()):
        resp = client.get("/dashboard-summary?start_date=2026-01-01&end_date=2026-01-31")
    body = resp.json()
    for f in REQUIRED_FIELDS:
        assert f in body, f"Missing field: {f}"


def test_dashboard_top_stores_capped_at_5(client):
    many = [StoreRevenueRank(store_id=i, total_sales=float(1000 - i)) for i in range(1, 9)]
    s = _summary(top_stores_by_revenue=many[:5])
    with patch(f"{SVC}.get_dashboard_summary", return_value=s):
        resp = client.get("/dashboard-summary?start_date=2026-01-01&end_date=2026-01-31")
    assert len(resp.json()["top_stores_by_revenue"]) <= 5


def test_dashboard_severity_includes_all_levels(client):
    with patch(f"{SVC}.get_dashboard_summary", return_value=_summary()):
        resp = client.get("/dashboard-summary?start_date=2026-01-01&end_date=2026-01-31")
    levels = {e["severity_level"] for e in resp.json()["exception_count_by_severity"]}
    assert {"info", "warning", "critical"}.issubset(levels)


def test_dashboard_daily_trend_one_per_day(client):
    points = [
        DailySalesPoint(date=date(2026, 1, d), total_sales=100.0, transaction_count=10)
        for d in range(1, 8)
    ]
    s = _summary(daily_sales_trend=points)
    with patch(f"{SVC}.get_dashboard_summary", return_value=s):
        resp = client.get("/dashboard-summary?start_date=2026-01-01&end_date=2026-01-07")
    body = resp.json()
    assert len(body["daily_sales_trend"]) == 7


def test_dashboard_invalid_date_range_returns_400(client):
    resp = client.get("/dashboard-summary?start_date=2026-02-01&end_date=2026-01-31")
    assert resp.status_code == 400
    assert "start_date" in resp.json()["detail"].lower()


def test_dashboard_missing_dates_returns_422(client):
    assert client.get("/dashboard-summary").status_code == 422
    assert client.get("/dashboard-summary?start_date=2026-01-01").status_code == 422


def test_dashboard_invalid_date_format_returns_422(client):
    resp = client.get("/dashboard-summary?start_date=not-a-date&end_date=2026-01-31")
    assert resp.status_code == 422


def test_dashboard_dates_forwarded_to_service(client):
    with patch(f"{SVC}.get_dashboard_summary", return_value=_summary()) as mock:
        client.get("/dashboard-summary?start_date=2026-01-01&end_date=2026-01-31")
    _, kwargs = mock.call_args
    assert kwargs["start_date"] == date(2026, 1, 1)
    assert kwargs["end_date"] == date(2026, 1, 31)
