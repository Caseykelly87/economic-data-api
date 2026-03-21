from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.economic import GdpOut, InflationOut, UnemploymentOut
from app.services import economic as svc

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/inflation", response_model=list[InflationOut])
def get_inflation(
    start_date: date | None = Query(default=None, description="Filter observations on or after this date"),
    end_date: date | None = Query(default=None, description="Filter observations on or before this date"),
    series_id: str | None = Query(default=None, description="Return only the specified series"),
    db: Session = Depends(get_db),
):
    """Inflation-related series from the inflation mart."""
    return svc.get_inflation_series(db, start_date=start_date, end_date=end_date, series_id=series_id)


@router.get("/unemployment", response_model=list[UnemploymentOut])
def get_unemployment(
    start_date: date | None = Query(default=None, description="Filter observations on or after this date"),
    end_date: date | None = Query(default=None, description="Filter observations on or before this date"),
    series_id: str | None = Query(default=None, description="Return only the specified series"),
    db: Session = Depends(get_db),
):
    """Labor-market series (wages, employment) from the labor market mart."""
    return svc.get_unemployment_series(db, start_date=start_date, end_date=end_date, series_id=series_id)


@router.get("/gdp", response_model=list[GdpOut])
def get_gdp(
    start_date: date | None = Query(default=None, description="Filter observations on or after this date"),
    end_date: date | None = Query(default=None, description="Filter observations on or before this date"),
    series_id: str | None = Query(default=None, description="Return only the specified series"),
    db: Session = Depends(get_db),
):
    """GDP-related series from the GDP mart."""
    return svc.get_gdp_series(db, start_date=start_date, end_date=end_date, series_id=series_id)
