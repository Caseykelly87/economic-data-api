from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from app.schemas.grocery import PaginatedAnomaliesOut
from app.services import grocery as svc

SeverityLiteral = Literal["info", "warning", "critical"]
RuleLiteral = Literal["revenue_band", "labor_pct_band", "transactions_band"]

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("", response_model=PaginatedAnomaliesOut)
def list_anomalies(
    start_date: date | None = Query(
        default=None, description="Filter rows on or after this date (YYYY-MM-DD)"
    ),
    end_date: date | None = Query(
        default=None, description="Filter rows on or before this date (YYYY-MM-DD)"
    ),
    store_id: int | None = Query(
        default=None, ge=1, le=8, description="Filter to a single store (1–8)"
    ),
    severity_level: SeverityLiteral | None = Query(
        default=None,
        description="Filter to a severity level: info, warning, or critical",
    ),
    rule_id: RuleLiteral | None = Query(
        default=None,
        description="Filter to a detection rule: revenue_band, "
                    "labor_pct_band, or transactions_band",
    ),
    limit: int = Query(
        default=50, ge=1, le=200, description="Number of rows to return (1–200)"
    ),
    offset: int = Query(default=0, ge=0, description="Number of rows to skip"),
):
    """List anomaly flag rows, filterable by date, store, severity,
    and rule, with pagination."""
    total, items = svc.get_anomalies(
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
        severity_level=severity_level,
        rule_id=rule_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedAnomaliesOut(total=total, limit=limit, offset=offset, items=items)
