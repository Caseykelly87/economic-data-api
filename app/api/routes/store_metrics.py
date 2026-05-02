from datetime import date

import structlog
from fastapi import APIRouter, Query

from app.schemas.grocery import PaginatedStoreMetricsOut
from app.services import grocery as svc

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/store-metrics", tags=["store-metrics"])


@router.get("", response_model=PaginatedStoreMetricsOut)
def list_store_metrics(
    start_date: date | None = Query(
        default=None, description="Filter rows on or after this date (YYYY-MM-DD)"
    ),
    end_date: date | None = Query(
        default=None, description="Filter rows on or before this date (YYYY-MM-DD)"
    ),
    store_id: int | None = Query(
        default=None, ge=1, le=8, description="Filter to a single store (1–8)"
    ),
    limit: int = Query(
        default=50, ge=1, le=200, description="Number of rows to return (1–200)"
    ),
    offset: int = Query(default=0, ge=0, description="Number of rows to skip"),
):
    """List store-daily metric rows, filterable by date range and
    store, with pagination."""
    total, items = svc.get_store_metrics(
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedStoreMetricsOut(total=total, limit=limit, offset=offset, items=items)
