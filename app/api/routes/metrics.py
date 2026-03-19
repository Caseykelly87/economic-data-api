from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.economic import InflationOut, UnemploymentOut
from app.services import economic as svc

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/inflation", response_model=list[InflationOut])
def get_inflation(db: Session = Depends(get_db)):
    return svc.get_inflation_series(db)


@router.get("/unemployment", response_model=list[UnemploymentOut])
def get_unemployment(db: Session = Depends(get_db)):
    return svc.get_unemployment_series(db)
