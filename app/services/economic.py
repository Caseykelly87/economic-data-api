from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.economic import (
    DimSeries,
    FactObservation,
    MartEconomicSummary,
    MartGdp,
    MartInflation,
    MartLaborMarket,
)
from app.schemas.economic import (
    GdpOut,
    InflationOut,
    KeyIndicator,
    ObservationOut,
    SeriesDetailOut,
    SeriesOut,
    SummaryOut,
    UnemploymentOut,
)


def _parse_date(date_str: str) -> date | None:
    """Parse date string from raw.fact_economic_observations (stored as text)."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _group_mart_rows(rows, out_schema):
    """
    Group mart-table rows by series_id, compute the latest observation per
    series, and return a list of ``out_schema`` instances.
    """
    grouped: dict[str, dict] = {}
    for row in rows:
        if row.series_id not in grouped:
            grouped[row.series_id] = {
                "series_id": row.series_id,
                "series_name": row.series_name,
                "source": row.source,
                "observations": [],
            }
        grouped[row.series_id]["observations"].append(
            ObservationOut(observation_date=row.observation_date, value=row.value)
        )
    result = []
    for g in grouped.values():
        obs = g["observations"]
        latest = max(obs, key=lambda o: o.observation_date) if obs else None
        result.append(
            out_schema(
                series_id=g["series_id"],
                series_name=g["series_name"],
                source=g["source"],
                latest_date=latest.observation_date if latest else None,
                latest_value=latest.value if latest else None,
                observations=obs,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

def get_all_series(
    db: Session,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[SeriesOut]]:
    """Return (total_count, page_of_series) from raw.dim_series."""
    total: int = db.execute(select(func.count()).select_from(DimSeries)).scalar_one()
    rows = db.execute(select(DimSeries).limit(limit).offset(offset)).scalars().all()
    return total, [SeriesOut.model_validate(r) for r in rows]


def get_series_by_id(
    db: Session,
    series_id: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> SeriesDetailOut | None:
    """Return series metadata and its observations, optionally filtered by date range."""
    series = (
        db.execute(select(DimSeries).where(DimSeries.series_id == series_id))
        .scalars()
        .first()
    )
    if series is None:
        return None

    obs_rows = (
        db.execute(
            select(FactObservation)
            .where(FactObservation.series_id == series_id)
            .order_by(FactObservation.date)
        )
        .scalars()
        .all()
    )

    observations = []
    for row in obs_rows:
        parsed = _parse_date(row.date)
        if parsed is None:
            continue
        if start_date and parsed < start_date:
            continue
        if end_date and parsed > end_date:
            continue
        observations.append(ObservationOut(observation_date=parsed, value=row.value))

    return SeriesDetailOut(
        series_id=series.series_id,
        series_name=series.series_name,
        source=series.source,
        observations=observations,
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _apply_mart_filters(query, model, series_id, start_date, end_date):
    """Apply optional filters to a mart SELECT query."""
    if series_id:
        query = query.where(model.series_id == series_id)
    if start_date:
        query = query.where(model.observation_date >= start_date)
    if end_date:
        query = query.where(model.observation_date <= end_date)
    return query


def get_inflation_series(
    db: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    series_id: str | None = None,
) -> list[InflationOut]:
    q = select(MartInflation).order_by(MartInflation.series_id, MartInflation.observation_date)
    q = _apply_mart_filters(q, MartInflation, series_id, start_date, end_date)
    rows = db.execute(q).scalars().all()
    return _group_mart_rows(rows, InflationOut)


def get_unemployment_series(
    db: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    series_id: str | None = None,
) -> list[UnemploymentOut]:
    q = select(MartLaborMarket).order_by(MartLaborMarket.series_id, MartLaborMarket.observation_date)
    q = _apply_mart_filters(q, MartLaborMarket, series_id, start_date, end_date)
    rows = db.execute(q).scalars().all()
    return _group_mart_rows(rows, UnemploymentOut)


def get_gdp_series(
    db: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    series_id: str | None = None,
) -> list[GdpOut]:
    q = select(MartGdp).order_by(MartGdp.series_id, MartGdp.observation_date)
    q = _apply_mart_filters(q, MartGdp, series_id, start_date, end_date)
    rows = db.execute(q).scalars().all()
    return _group_mart_rows(rows, GdpOut)


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def get_summary(db: Session) -> SummaryOut:
    """Return all rows from mart_economic_summary as a summary of key indicators."""
    rows = db.execute(select(MartEconomicSummary)).scalars().all()
    return SummaryOut(indicators=[KeyIndicator.model_validate(r) for r in rows])
