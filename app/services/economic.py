from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.economic import (
    DimSeries,
    FactObservation,
    MartInflation,
    MartLaborMarket,
    MartEconomicSummary,
)
from app.schemas.economic import (
    SeriesOut,
    SeriesDetailOut,
    ObservationOut,
    InflationOut,
    UnemploymentOut,
    KeyIndicator,
    SummaryOut,
)


def _parse_date(date_str: str):
    """Parse date string from raw.fact_economic_observations (stored as text)."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _group_mart_rows(rows, out_schema):
    """Group mart table rows by series_id, compute latest obs, return list of out_schema."""
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


def get_all_series(db: Session) -> list[SeriesOut]:
    rows = db.execute(select(DimSeries)).scalars().all()
    return [SeriesOut.model_validate(r) for r in rows]


def get_series_by_id(db: Session, series_id: str) -> SeriesDetailOut | None:
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
        if parsed:
            observations.append(ObservationOut(observation_date=parsed, value=row.value))
    return SeriesDetailOut(
        series_id=series.series_id,
        series_name=series.series_name,
        source=series.source,
        observations=observations,
    )


def get_inflation_series(db: Session) -> list[InflationOut]:
    rows = (
        db.execute(
            select(MartInflation).order_by(MartInflation.series_id, MartInflation.observation_date)
        )
        .scalars()
        .all()
    )
    return _group_mart_rows(rows, InflationOut)


def get_unemployment_series(db: Session) -> list[UnemploymentOut]:
    rows = (
        db.execute(
            select(MartLaborMarket).order_by(MartLaborMarket.series_id, MartLaborMarket.observation_date)
        )
        .scalars()
        .all()
    )
    return _group_mart_rows(rows, UnemploymentOut)


def get_summary(db: Session) -> SummaryOut:
    rows = db.execute(select(MartEconomicSummary)).scalars().all()
    return SummaryOut(indicators=[KeyIndicator.model_validate(r) for r in rows])
