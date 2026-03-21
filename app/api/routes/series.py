from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.economic import PaginatedSeriesOut, SeriesDetailOut
from app.services import economic as svc

router = APIRouter(prefix="/series", tags=["series"])


@router.get("", response_model=PaginatedSeriesOut)
def list_series(
    limit: int = Query(default=50, ge=1, le=200, description="Number of series to return (1–200)"),
    offset: int = Query(default=0, ge=0, description="Number of series to skip"),
    db: Session = Depends(get_db),
):
    """List all available economic series with pagination."""
    total, items = svc.get_all_series(db, limit=limit, offset=offset)
    return PaginatedSeriesOut(total=total, limit=limit, offset=offset, items=items)


@router.get("/{series_id}", response_model=SeriesDetailOut)
def get_series(
    series_id: str,
    start_date: date | None = Query(default=None, description="Filter observations on or after this date"),
    end_date: date | None = Query(default=None, description="Filter observations on or before this date"),
    db: Session = Depends(get_db),
):
    """Get metadata and observations for a single series, optionally filtered by date range."""
    result = svc.get_series_by_id(db, series_id, start_date=start_date, end_date=end_date)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Series '{series_id}' not found.")
    return result
