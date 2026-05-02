from datetime import date

import structlog
from fastapi import APIRouter, HTTPException, Query

from app.schemas.grocery import DashboardSummaryOut
from app.services import grocery as svc

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboard-summary", tags=["dashboard"])


@router.get("", response_model=DashboardSummaryOut)
def get_dashboard_summary(
    start_date: date = Query(..., description="Start of the summary window (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End of the summary window (YYYY-MM-DD)"),
):
    """Composed KPI overview for the portal dashboard: totals,
    top-store rankings, exception counts by severity, and a daily
    sales trend across the supplied date range."""
    if start_date > end_date:
        logger.warning(
            "dashboard_invalid_date_range",
            start_date=str(start_date),
            end_date=str(end_date),
        )
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date.",
        )
    return svc.get_dashboard_summary(start_date=start_date, end_date=end_date)
