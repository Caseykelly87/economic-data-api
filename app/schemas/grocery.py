from datetime import date

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# store_daily_metrics rows
# ---------------------------------------------------------------------------

class StoreMetricOut(BaseModel):
    date: date
    store_id: int
    total_sales: float
    transaction_count: int
    avg_basket_size: float | None
    labor_cost_pct: float | None

    model_config = {"from_attributes": True}


class PaginatedStoreMetricsOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[StoreMetricOut]


# ---------------------------------------------------------------------------
# department_daily_metrics rows
# ---------------------------------------------------------------------------

class DepartmentMetricOut(BaseModel):
    date: date
    store_id: int
    department_id: int
    net_sales: float
    transactions: int
    units_sold: int
    gross_margin_pct: float

    model_config = {"from_attributes": True}


class PaginatedDepartmentMetricsOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[DepartmentMetricOut]


# ---------------------------------------------------------------------------
# dim_stores rows
# ---------------------------------------------------------------------------

class StoreDimensionOut(BaseModel):
    store_id: int
    store_name: str
    address: str
    city: str
    zip: str  # 5-character zero-padded string; coerced from int64 in service layer
    county_fips: str  # 5-character zero-padded string; coerced from int64 in service layer
    trade_area_profile: str
    sqft: int
    open_date: date
    base_daily_revenue: float

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# anomaly_flags rows
# ---------------------------------------------------------------------------

class AnomalyFlagOut(BaseModel):
    date: date
    store_id: int
    rule_id: str
    actual_value: float
    expected_low: float
    expected_high: float
    distance_from_band: float
    severity_score: float
    severity_level: str

    model_config = {"from_attributes": True}


class PaginatedAnomaliesOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AnomalyFlagOut]


# ---------------------------------------------------------------------------
# /dashboard-summary
# ---------------------------------------------------------------------------

class StoreRevenueRank(BaseModel):
    store_id: int
    total_sales: float


class SeverityCount(BaseModel):
    severity_level: str
    count: int


class DailySalesPoint(BaseModel):
    date: date
    total_sales: float
    transaction_count: int


class DashboardSummaryOut(BaseModel):
    start_date: date
    end_date: date
    total_sales: float
    total_transactions: int
    average_labor_cost_pct: float | None
    top_stores_by_revenue: list[StoreRevenueRank]
    exception_count_by_severity: list[SeverityCount]
    daily_sales_trend: list[DailySalesPoint]
