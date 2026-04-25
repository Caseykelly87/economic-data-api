"""Service layer for grocery endpoints. Reads from parquet files
configured via app.core.config.settings.resolved_*_path properties.
"""
from datetime import date
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.schemas.grocery import (
    AnomalyFlagOut,
    DailySalesPoint,
    DashboardSummaryOut,
    SeverityCount,
    StoreMetricOut,
    StoreRevenueRank,
)


SEVERITY_LEVELS = ("info", "warning", "critical")


# ---------------------------------------------------------------------------
# Parquet loaders
# ---------------------------------------------------------------------------

def load_store_metrics_df() -> pd.DataFrame:
    """Read the resolved store_daily_metrics parquet into a DataFrame."""
    path = settings.resolved_store_metrics_path
    if not Path(path).is_file():
        raise FileNotFoundError(
            f"store_daily_metrics parquet not found at '{path}'."
        )
    return pd.read_parquet(path)


def load_anomaly_flags_df() -> pd.DataFrame:
    """Read the resolved anomaly_flags parquet into a DataFrame."""
    path = settings.resolved_anomaly_flags_path
    if not Path(path).is_file():
        raise FileNotFoundError(
            f"anomaly_flags parquet not found at '{path}'."
        )
    return pd.read_parquet(path)


def _filter_dates(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    if start_date is not None:
        df = df[df["date"] >= start_date]
    if end_date is not None:
        df = df[df["date"] <= end_date]
    return df


# ---------------------------------------------------------------------------
# /store-metrics
# ---------------------------------------------------------------------------

def get_store_metrics(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    store_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[StoreMetricOut]]:
    """Return (total, page) of store_daily_metrics rows after filters."""
    df = load_store_metrics_df()
    df = _filter_dates(df, start_date, end_date)
    if store_id is not None:
        df = df[df["store_id"] == store_id]

    total = int(len(df))
    if total == 0:
        return 0, []

    df = df.sort_values(["date", "store_id"]).reset_index(drop=True)
    page = df.iloc[offset : offset + limit]
    items = [StoreMetricOut.model_validate(r) for r in page.to_dict(orient="records")]
    return total, items


# ---------------------------------------------------------------------------
# /anomalies
# ---------------------------------------------------------------------------

def get_anomalies(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    store_id: int | None = None,
    severity_level: str | None = None,
    rule_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[AnomalyFlagOut]]:
    """Return (total, page) of anomaly_flags rows after filters."""
    df = load_anomaly_flags_df()
    df = _filter_dates(df, start_date, end_date)
    if store_id is not None:
        df = df[df["store_id"] == store_id]
    if severity_level is not None:
        df = df[df["severity_level"] == severity_level]
    if rule_id is not None:
        df = df[df["rule_id"] == rule_id]

    total = int(len(df))
    if total == 0:
        return 0, []

    df = df.sort_values(["date", "store_id", "rule_id"]).reset_index(drop=True)
    page = df.iloc[offset : offset + limit]
    items = [AnomalyFlagOut.model_validate(r) for r in page.to_dict(orient="records")]
    return total, items


# ---------------------------------------------------------------------------
# /dashboard-summary
# ---------------------------------------------------------------------------

def get_dashboard_summary(
    *,
    start_date: date,
    end_date: date,
) -> DashboardSummaryOut:
    """Compose KPI totals, top-store rankings, severity counts, and
    daily sales trend into a single response."""
    metrics = load_store_metrics_df()
    flags = load_anomaly_flags_df()

    metrics = _filter_dates(metrics, start_date, end_date)
    flags = _filter_dates(flags, start_date, end_date)

    if metrics.empty:
        total_sales = 0.0
        total_transactions = 0
        avg_labor = None
        top_stores: list[StoreRevenueRank] = []
        trend: list[DailySalesPoint] = []
    else:
        total_sales = round(float(metrics["total_sales"].sum()), 2)
        total_transactions = int(metrics["transaction_count"].sum())
        labor_mean = metrics["labor_cost_pct"].mean(skipna=True)
        avg_labor = None if pd.isna(labor_mean) else round(float(labor_mean), 6)

        store_totals = (
            metrics.groupby("store_id")["total_sales"].sum().sort_values(ascending=False)
        )
        top_stores = [
            StoreRevenueRank(store_id=int(sid), total_sales=round(float(v), 2))
            for sid, v in store_totals.head(5).items()
        ]

        daily = (
            metrics.groupby("date")
            .agg(total_sales=("total_sales", "sum"),
                 transaction_count=("transaction_count", "sum"))
            .sort_index()
        )
        trend = [
            DailySalesPoint(
                date=d,
                total_sales=round(float(row.total_sales), 2),
                transaction_count=int(row.transaction_count),
            )
            for d, row in daily.iterrows()
        ]

    severity_counts = {lvl: 0 for lvl in SEVERITY_LEVELS}
    if not flags.empty:
        observed = flags["severity_level"].value_counts().to_dict()
        for lvl, count in observed.items():
            severity_counts[lvl] = int(count)
    exception_counts = [
        SeverityCount(severity_level=lvl, count=severity_counts[lvl])
        for lvl in SEVERITY_LEVELS
    ]

    return DashboardSummaryOut(
        start_date=start_date,
        end_date=end_date,
        total_sales=total_sales,
        total_transactions=total_transactions,
        average_labor_cost_pct=avg_labor,
        top_stores_by_revenue=top_stores,
        exception_count_by_severity=exception_counts,
        daily_sales_trend=trend,
    )
