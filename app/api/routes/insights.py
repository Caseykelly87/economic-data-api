from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.economic import SummaryOut
from app.services import economic as svc

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/summary", response_model=SummaryOut)
def get_summary(db: Session = Depends(get_db)):
    return svc.get_summary(db)
