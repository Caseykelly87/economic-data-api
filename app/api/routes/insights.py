from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.economic import SummaryOut
from app.schemas.insights import DetectionQualityOut
from app.services import economic as economic_svc
from app.services import insights as insights_svc

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/summary", response_model=SummaryOut)
def get_summary(db: Session = Depends(get_db)):
    return economic_svc.get_summary(db)


@router.get("/detection-quality", response_model=DetectionQualityOut)
def get_detection_quality():
    """Detection-quality measurement against the sim engine's
    ground-truth anomaly log. Returns global recall, false-positive
    rate, per-anomaly-type recall, and a pass/fail verdict against
    the phase 2 contract."""
    return insights_svc.get_detection_quality()
