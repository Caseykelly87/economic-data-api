import structlog
from fastapi import APIRouter

from app.schemas.grocery import StoreDimensionOut
from app.services import grocery as svc

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dim-stores", tags=["dim-stores"])


@router.get("", response_model=list[StoreDimensionOut])
def list_dim_stores():
    """Return all store dimension rows.

    Reference data for the 8 stores in the grocery dataset. The full
    payload is returned as a flat array (no pagination — the dataset
    is tiny). Sorted by ``store_id``.

    Fields:
    - ``store_id``: integer 1-8
    - ``store_name``: display name
    - ``address``, ``city``: location details
    - ``zip``, ``county_fips``: 5-character zero-padded identifier strings
    - ``trade_area_profile``: one of ``suburban-family``, ``urban-dense``,
      ``value-market``
    - ``sqft``: store square footage
    - ``open_date``: ISO date
    - ``base_daily_revenue``: simulation engine baseline parameter
    """
    return svc.get_dim_stores()
