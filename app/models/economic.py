from datetime import date
from decimal import Decimal

from sqlalchemy import String, Date, Numeric, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EconomicSeries(Base):
    """
    Represents a named economic data series (e.g., CPI, Unemployment Rate).
    Maps to the mart table populated by the ETL service.
    """
    __tablename__ = "economic_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(32), nullable=True)

    observations: Mapped[list["SeriesObservation"]] = relationship(
        "SeriesObservation", back_populates="series", lazy="select"
    )


class SeriesObservation(Base):
    """
    A single data point for an economic series on a given date.
    Maps to the mart table populated by the ETL service.
    """
    __tablename__ = "series_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(Integer, ForeignKey("economic_series.id"), nullable=False, index=True)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    series: Mapped["EconomicSeries"] = relationship("EconomicSeries", back_populates="observations")
