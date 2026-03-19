from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.economic import EconomicSeries, SeriesObservation
from app.schemas.economic import (
    SeriesOut,
    SeriesDetailOut,
    ObservationOut,
    InflationOut,
    UnemploymentOut,
    KeyIndicator,
    SummaryOut,
)


def _latest_obs(observations: list[SeriesObservation]) -> SeriesObservation | None:
    if not observations:
        return None
    return max(observations, key=lambda o: o.observation_date)


def get_all_series(db: Session) -> list[SeriesOut]:
    rows = db.execute(select(EconomicSeries)).scalars().all()
    return [SeriesOut.model_validate(r) for r in rows]


def get_series_by_id(db: Session, series_id: str) -> SeriesDetailOut | None:
    row = (
        db.execute(select(EconomicSeries).where(EconomicSeries.series_id == series_id))
        .scalars()
        .first()
    )
    if row is None:
        return None
    return SeriesDetailOut(
        series_id=row.series_id,
        name=row.name,
        description=row.description,
        category=row.category,
        unit=row.unit,
        frequency=row.frequency,
        observations=[
            ObservationOut(observation_date=o.observation_date, value=o.value)
            for o in row.observations
        ],
    )


def get_inflation_series(db: Session) -> list[InflationOut]:
    rows = (
        db.execute(select(EconomicSeries).where(EconomicSeries.category == "inflation"))
        .scalars()
        .all()
    )
    result = []
    for row in rows:
        latest = _latest_obs(row.observations)
        result.append(
            InflationOut(
                series_id=row.series_id,
                name=row.name,
                unit=row.unit,
                latest_date=latest.observation_date if latest else None,
                latest_value=latest.value if latest else None,
                observations=[
                    ObservationOut(observation_date=o.observation_date, value=o.value)
                    for o in row.observations
                ],
            )
        )
    return result


def get_unemployment_series(db: Session) -> list[UnemploymentOut]:
    rows = (
        db.execute(select(EconomicSeries).where(EconomicSeries.category == "unemployment"))
        .scalars()
        .all()
    )
    result = []
    for row in rows:
        latest = _latest_obs(row.observations)
        result.append(
            UnemploymentOut(
                series_id=row.series_id,
                name=row.name,
                unit=row.unit,
                latest_date=latest.observation_date if latest else None,
                latest_value=latest.value if latest else None,
                observations=[
                    ObservationOut(observation_date=o.observation_date, value=o.value)
                    for o in row.observations
                ],
            )
        )
    return result


def get_summary(db: Session) -> SummaryOut:
    rows = db.execute(select(EconomicSeries)).scalars().all()
    indicators = []
    for row in rows:
        latest = _latest_obs(row.observations)
        indicators.append(
            KeyIndicator(
                series_id=row.series_id,
                name=row.name,
                unit=row.unit,
                latest_date=latest.observation_date if latest else None,
                latest_value=latest.value if latest else None,
            )
        )
    return SummaryOut(indicators=indicators)
