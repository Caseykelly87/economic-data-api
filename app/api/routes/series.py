from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.economic import SeriesOut, SeriesDetailOut
from app.services import economic as svc

router = APIRouter(prefix="/series", tags=["series"])


@router.get("", response_model=list[SeriesOut])
def list_series(db: Session = Depends(get_db)):
    return svc.get_all_series(db)


@router.get("/{series_id}", response_model=SeriesDetailOut)
def get_series(series_id: str, db: Session = Depends(get_db)):
    result = svc.get_series_by_id(db, series_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Series '{series_id}' not found.")
    return result
