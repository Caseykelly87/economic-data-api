"""Tests for app.services.grocery.

Use the bundled demo fixtures as input; no live data path is required.
"""
from datetime import date

import pandas as pd
import pytest

from app.services import grocery as svc
from app.schemas.grocery import (
    AnomalyFlagOut,
    DashboardSummaryOut,
    StoreMetricOut,
)


METRICS_COLS = {
    "date", "store_id", "total_sales", "transaction_count",
    "avg_basket_size", "labor_cost_pct",
}
FLAG_COLS = {
    "date", "store_id", "rule_id", "actual_value",
    "expected_low", "expected_high", "distance_from_band",
    "severity_score", "severity_level",
}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def test_load_store_metrics_df_returns_dataframe():
    df = svc.load_store_metrics_df()
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == METRICS_COLS
    assert len(df) > 0


def test_load_anomaly_flags_df_returns_dataframe():
    df = svc.load_anomaly_flags_df()
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == FLAG_COLS
    assert len(df) > 0


def test_load_store_metrics_raises_when_path_missing(monkeypatch):
    monkeypatch.setattr(
        svc.settings, "GROCERY_FIXTURES_DIR", "does/not/exist", raising=False
    )
    monkeypatch.setattr(svc.settings, "STORE_METRICS_PATH", None, raising=False)
    with pytest.raises(FileNotFoundError):
        svc.load_store_metrics_df()


def test_load_anomaly_flags_raises_when_path_missing(monkeypatch):
    monkeypatch.setattr(
        svc.settings, "GROCERY_FIXTURES_DIR", "does/not/exist", raising=False
    )
    monkeypatch.setattr(svc.settings, "ANOMALY_FLAGS_PATH", None, raising=False)
    with pytest.raises(FileNotFoundError):
        svc.load_anomaly_flags_df()


# ---------------------------------------------------------------------------
# get_store_metrics
# ---------------------------------------------------------------------------

def test_get_store_metrics_returns_total_and_items():
    total, items = svc.get_store_metrics(limit=10, offset=0)
    assert isinstance(total, int)
    assert total > 0
    assert isinstance(items, list)
    assert all(isinstance(item, StoreMetricOut) for item in items)
    assert len(items) <= 10


def test_get_store_metrics_pagination_honored():
    total_full, _ = svc.get_store_metrics(limit=1, offset=0)
    _, page_a = svc.get_store_metrics(limit=5, offset=0)
    _, page_b = svc.get_store_metrics(limit=5, offset=5)
    assert len(page_a) == 5
    assert len(page_b) == 5
    assert page_a[0] != page_b[0]
    assert total_full > 0


def test_get_store_metrics_date_range_filter():
    df = svc.load_store_metrics_df()
    min_date = min(df["date"])
    max_date = max(df["date"])
    total, _ = svc.get_store_metrics(
        start_date=min_date, end_date=max_date, limit=1, offset=0
    )
    assert total == len(df)


def test_get_store_metrics_store_id_filter():
    total, items = svc.get_store_metrics(store_id=1, limit=500, offset=0)
    assert total > 0
    for item in items:
        assert item.store_id == 1


def test_get_store_metrics_combined_filters_compose():
    df = svc.load_store_metrics_df()
    sample_date = max(df["date"])
    total, items = svc.get_store_metrics(
        start_date=sample_date, end_date=sample_date, store_id=2, limit=10
    )
    assert total == 1
    assert items[0].store_id == 2
    assert items[0].date == sample_date


def test_get_store_metrics_empty_when_no_match():
    impossible = date(1900, 1, 1)
    total, items = svc.get_store_metrics(
        start_date=impossible, end_date=impossible
    )
    assert total == 0
    assert items == []


# ---------------------------------------------------------------------------
# get_anomalies
# ---------------------------------------------------------------------------

def test_get_anomalies_returns_total_and_items():
    total, items = svc.get_anomalies(limit=200, offset=0)
    assert isinstance(total, int)
    assert total > 0
    assert all(isinstance(item, AnomalyFlagOut) for item in items)


def test_get_anomalies_severity_filter():
    df = svc.load_anomaly_flags_df()
    target = df["severity_level"].iloc[0]
    total, items = svc.get_anomalies(severity_level=target, limit=200, offset=0)
    assert total > 0
    for item in items:
        assert item.severity_level == target


def test_get_anomalies_rule_filter():
    df = svc.load_anomaly_flags_df()
    target = df["rule_id"].iloc[0]
    total, items = svc.get_anomalies(rule_id=target, limit=200, offset=0)
    assert total > 0
    for item in items:
        assert item.rule_id == target


def test_get_anomalies_date_range_filter():
    df = svc.load_anomaly_flags_df()
    min_date = min(df["date"])
    max_date = max(df["date"])
    total, _ = svc.get_anomalies(start_date=min_date, end_date=max_date, limit=1)
    assert total == len(df)


def test_get_anomalies_store_id_filter():
    df = svc.load_anomaly_flags_df()
    target = int(df["store_id"].iloc[0])
    total, items = svc.get_anomalies(store_id=target, limit=200)
    assert total > 0
    for item in items:
        assert item.store_id == target


def test_get_anomalies_pagination_honored():
    _, page_a = svc.get_anomalies(limit=2, offset=0)
    _, page_b = svc.get_anomalies(limit=2, offset=2)
    assert len(page_a) == 2
    assert len(page_b) == 2
    assert page_a[0] != page_b[0]


def test_get_anomalies_empty_when_no_match():
    impossible = date(1900, 1, 1)
    total, items = svc.get_anomalies(start_date=impossible, end_date=impossible)
    assert total == 0
    assert items == []


# ---------------------------------------------------------------------------
# get_dashboard_summary
# ---------------------------------------------------------------------------

def test_dashboard_summary_returns_pydantic_model():
    df = svc.load_store_metrics_df()
    start = min(df["date"])
    end = max(df["date"])
    summary = svc.get_dashboard_summary(start_date=start, end_date=end)
    assert isinstance(summary, DashboardSummaryOut)


def test_dashboard_summary_required_fields():
    df = svc.load_store_metrics_df()
    start = min(df["date"])
    end = max(df["date"])
    s = svc.get_dashboard_summary(start_date=start, end_date=end)
    assert s.start_date == start
    assert s.end_date == end
    assert s.total_sales > 0
    assert s.total_transactions > 0
    assert s.average_labor_cost_pct is not None


def test_dashboard_summary_top_stores_capped_at_5():
    df = svc.load_store_metrics_df()
    start = min(df["date"])
    end = max(df["date"])
    s = svc.get_dashboard_summary(start_date=start, end_date=end)
    assert len(s.top_stores_by_revenue) <= 5
    sales = [r.total_sales for r in s.top_stores_by_revenue]
    assert sales == sorted(sales, reverse=True)


def test_dashboard_summary_severity_counts_include_all_levels():
    df = svc.load_store_metrics_df()
    start = min(df["date"])
    end = max(df["date"])
    s = svc.get_dashboard_summary(start_date=start, end_date=end)
    levels = {entry.severity_level for entry in s.exception_count_by_severity}
    assert {"info", "warning", "critical"}.issubset(levels)


def test_dashboard_summary_severity_zeros_when_empty_range():
    impossible = date(1900, 1, 1)
    s = svc.get_dashboard_summary(start_date=impossible, end_date=impossible)
    counts = {e.severity_level: e.count for e in s.exception_count_by_severity}
    assert counts == {"info": 0, "warning": 0, "critical": 0}


def test_dashboard_summary_daily_trend_one_per_day():
    df = svc.load_store_metrics_df()
    sorted_dates = sorted(df["date"].unique())
    start = sorted_dates[0]
    end = sorted_dates[6]
    s = svc.get_dashboard_summary(start_date=start, end_date=end)
    assert len(s.daily_sales_trend) == 7
    assert s.daily_sales_trend[0].date == start
    assert s.daily_sales_trend[-1].date == end


def test_dashboard_summary_empty_range_zero_totals():
    impossible = date(1900, 1, 1)
    s = svc.get_dashboard_summary(start_date=impossible, end_date=impossible)
    assert s.total_sales == 0
    assert s.total_transactions == 0
    assert s.average_labor_cost_pct is None
    assert s.top_stores_by_revenue == []
    assert s.daily_sales_trend == []
