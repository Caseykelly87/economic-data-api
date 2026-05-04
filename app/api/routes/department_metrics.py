from datetime import date

import structlog
from fastapi import APIRouter, Query

from app.schemas.grocery import PaginatedDepartmentMetricsOut
from app.services import grocery as svc

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/department-metrics", tags=["department-metrics"])


@router.get("", response_model=PaginatedDepartmentMetricsOut)
def list_department_metrics(
    start_date: date | None = Query(
        default=None, description="Filter rows on or after this date (YYYY-MM-DD)"
    ),
    end_date: date | None = Query(
        default=None, description="Filter rows on or before this date (YYYY-MM-DD)"
    ),
    store_id: int | None = Query(
        default=None, ge=1, le=8, description="Filter to a single store (1-8)"
    ),
    department_id: int | None = Query(
        default=None, ge=1, le=10, description="Filter to a single department (1-10)"
    ),
    limit: int = Query(
        default=50, ge=1, le=200, description="Number of rows to return (1-200)"
    ),
    offset: int = Query(default=0, ge=0, description="Number of rows to skip"),
):
    """List department-daily metric rows, filterable by date range,
    store, and department, with pagination.

    The grain is store-day-department: one row per (date, store_id,
    department_id) triple. The full canonical dataset has 14,706 rows
    covering 2025-07-01 through 2025-12-31 across 8 stores and 10
    departments.
    """
    total, items = svc.get_department_metrics(
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
        department_id=department_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedDepartmentMetricsOut(total=total, limit=limit, offset=offset, items=items)
