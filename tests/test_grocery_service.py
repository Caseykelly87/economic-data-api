"""Tests for app.services.grocery.

Use the bundled demo fixtures as input; no live data path is required.
"""
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from app.services import grocery as svc
from app.schemas.grocery import (
    AnomalyFlagOut,
    DashboardSummaryOut,
    StoreMetricOut,
)


@pytest.fixture(autouse=True)
def _isolate_grocery_caches():
    """Clear the parquet read caches before and after each test in this
    module. Tests that monkeypatch the resolved paths to non-existent
    directories must not see a stale cached DataFrame, and tests that
    assert disk read counts must start from a known-cold state."""
    svc._clear_grocery_caches()
    yield
    svc._clear_grocery_caches()


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
    # The bundled fixture is the ETL canonical store_daily_metrics parquet:
    # 8 stores across 2024-07-01..2025-12-31 (368 days) = 2944 store-days.
    assert len(df) == 2944
    # The read pipeline must preserve the canonical date dtype — rows carry
    # datetime.date objects, not strings — so date-range filters compare
    # correctly against the typed query parameters.
    assert isinstance(df["date"].iloc[0], date)
    # A known store-day value read directly off the canonical parquet.
    row = df[(df["store_id"] == 1) & (df["date"] == date(2024, 7, 1))].iloc[0]
    assert row["total_sales"] == 86429.35
    assert row["transaction_count"] == 2337


def test_load_anomaly_flags_df_returns_dataframe():
    df = svc.load_anomaly_flags_df()
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == FLAG_COLS
    # The bundled fixture is the ETL canonical anomaly_flags parquet.
    assert len(df) == 178
    assert isinstance(df["date"].iloc[0], date)
    # A known flag read off the canonical parquet: store 1's
    # gross_margin_band exception on 2024-07-14, where the gross margin
    # ratio reads 0.95 against an expected band ceiling of 0.62.
    flag = df[
        (df["store_id"] == 1)
        & (df["date"] == date(2024, 7, 14))
        & (df["rule_id"] == "gross_margin_band")
    ]
    assert len(flag) == 1
    assert flag.iloc[0]["actual_value"] == 0.95
    assert flag.iloc[0]["severity_level"] == "warning"


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
    # total is the full canonical row count, independent of the page size.
    assert total == 2944
    assert all(isinstance(item, StoreMetricOut) for item in items)
    assert len(items) == 10
    # The service sorts by (date, store_id), so the first page opens with
    # store 1 on the earliest canonical date.
    first = items[0]
    assert first.date == date(2024, 7, 1)
    assert first.store_id == 1
    assert first.total_sales == 86429.35
    assert first.transaction_count == 2337


def test_get_store_metrics_pagination_honored():
    total_full, _ = svc.get_store_metrics(limit=1, offset=0)
    _, page_a = svc.get_store_metrics(limit=5, offset=0)
    _, page_b = svc.get_store_metrics(limit=5, offset=5)
    assert total_full == 2944
    assert len(page_a) == 5
    assert len(page_b) == 5
    # Rows sort by (date, store_id). The first page is store-days 1-5 of the
    # opening canonical date; the second picks up at store 6 and rolls into
    # the next date once the eight stores are exhausted.
    assert [(r.date, r.store_id) for r in page_a] == [
        (date(2024, 7, 1), 1), (date(2024, 7, 1), 2), (date(2024, 7, 1), 3),
        (date(2024, 7, 1), 4), (date(2024, 7, 1), 5),
    ]
    assert [(r.date, r.store_id) for r in page_b] == [
        (date(2024, 7, 1), 6), (date(2024, 7, 1), 7), (date(2024, 7, 1), 8),
        (date(2024, 7, 2), 1), (date(2024, 7, 2), 2),
    ]


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
    # Full canonical anomaly_flags row count.
    assert total == 178
    assert len(items) == 178
    assert all(isinstance(item, AnomalyFlagOut) for item in items)
    # The service sorts by (date, store_id, rule_id); the first flag is
    # store 8's department_reconciliation exception on the earliest
    # flagged date.
    first = items[0]
    assert first.date == date(2024, 7, 2)
    assert first.store_id == 8
    assert first.rule_id == "department_reconciliation"
    assert first.actual_value == 50930.50


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
    # Rows sort by (date, store_id, rule_id); offset=2 advances exactly two
    # rows into that ordering.
    assert [(f.date, f.store_id, f.rule_id) for f in page_a] == [
        (date(2024, 7, 2), 8, "department_reconciliation"),
        (date(2024, 7, 4), 1, "department_reconciliation"),
    ]
    assert [(f.date, f.store_id, f.rule_id) for f in page_b] == [
        (date(2024, 7, 8), 7, "department_reconciliation"),
        (date(2024, 7, 10), 1, "department_reconciliation"),
    ]


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
    # Totals are independently derived by aggregating the canonical parquet,
    # matching the rounding the service applies, rather than snapshotting
    # whatever the summary currently emits.
    assert s.total_sales == round(float(df["total_sales"].sum()), 2)
    assert s.total_transactions == int(df["transaction_count"].sum())
    assert s.average_labor_cost_pct == round(
        float(df["labor_cost_pct"].mean()), 6
    )


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


# ---------------------------------------------------------------------------
# Parquet read caching
# ---------------------------------------------------------------------------

def test_load_store_metrics_df_caches_across_calls():
    """Business-correctness: a second call to load_store_metrics_df with
    the same resolved path must hit the lru_cache, not re-read the
    parquet from disk. The assertion is on the underlying pd.read_parquet
    call count — that the public loader's signature still returns a
    DataFrame is covered elsewhere."""
    with patch("app.services.grocery.pd.read_parquet", wraps=pd.read_parquet) as mock_read:
        svc.load_store_metrics_df()
        svc.load_store_metrics_df()
        assert mock_read.call_count == 1


def test_load_anomaly_flags_df_caches_across_calls():
    with patch("app.services.grocery.pd.read_parquet", wraps=pd.read_parquet) as mock_read:
        svc.load_anomaly_flags_df()
        svc.load_anomaly_flags_df()
        assert mock_read.call_count == 1


def test_load_department_metrics_df_caches_across_calls():
    with patch("app.services.grocery.pd.read_parquet", wraps=pd.read_parquet) as mock_read:
        svc.load_department_metrics_df()
        svc.load_department_metrics_df()
        assert mock_read.call_count == 1


def test_load_dim_stores_df_caches_across_calls():
    with patch("app.services.grocery.pd.read_parquet", wraps=pd.read_parquet) as mock_read:
        svc.load_dim_stores_df()
        svc.load_dim_stores_df()
        assert mock_read.call_count == 1


def test_clear_grocery_caches_forces_reload():
    """Business-correctness: after _clear_grocery_caches() the next
    loader call must re-read from disk. Without this guarantee the
    offline-vs-online mode-flip tests would silently serve stale cached
    DataFrames when the resolved path stays the same string."""
    with patch("app.services.grocery.pd.read_parquet", wraps=pd.read_parquet) as mock_read:
        svc.load_store_metrics_df()
        assert mock_read.call_count == 1
        svc._clear_grocery_caches()
        svc.load_store_metrics_df()
        assert mock_read.call_count == 2


def test_load_caches_keyed_on_resolved_path(monkeypatch, tmp_path):
    """Business-correctness: when the resolved path changes (the
    offline/online mode-flip case), the cache key changes and the next
    read serves the new file. Without re-keying on the path string, a
    test that flips STORE_METRICS_PATH would keep getting the prior
    DataFrame even though the underlying file is different."""
    # First read against the bundled fixture path.
    with patch("app.services.grocery.pd.read_parquet", wraps=pd.read_parquet) as mock_read:
        svc.load_store_metrics_df()
        assert mock_read.call_count == 1

        # Copy the same parquet to a new path and flip the live setting.
        # The bytes are identical but the path string differs, so the
        # cache must serve a fresh read at the new key.
        src = svc.settings.resolved_store_metrics_path
        dest = tmp_path / "store_daily_metrics.parquet"
        dest.write_bytes(__import__("pathlib").Path(src).read_bytes())
        monkeypatch.setattr(svc.settings, "STORE_METRICS_PATH", str(dest), raising=False)

        svc.load_store_metrics_df()
        assert mock_read.call_count == 2
