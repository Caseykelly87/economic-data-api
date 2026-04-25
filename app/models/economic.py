from datetime import date

from sqlalchemy import String, Date, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DimSeries(Base):
    __tablename__ = "dim_series"
    __table_args__ = {"schema": "raw"}

    series_id: Mapped[str] = mapped_column(String, primary_key=True)
    series_name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)


class FactObservation(Base):
    __tablename__ = "fact_economic_observations"
    __table_args__ = {"schema": "raw"}

    series_id: Mapped[str] = mapped_column(String, primary_key=True)
    series_name: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, primary_key=True)  # stored as text in DB
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)


class MartInflation(Base):
    __tablename__ = "mart_inflation"
    __table_args__ = {"schema": "public_analytics"}

    series_id: Mapped[str] = mapped_column(String, primary_key=True)
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    series_name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)


class MartLaborMarket(Base):
    __tablename__ = "mart_labor_market"
    __table_args__ = {"schema": "public_analytics"}

    series_id: Mapped[str] = mapped_column(String, primary_key=True)
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    series_name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)


class MartGdp(Base):
    __tablename__ = "mart_gdp"
    __table_args__ = {"schema": "public_analytics"}

    series_id: Mapped[str] = mapped_column(String, primary_key=True)
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    series_name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)


class MartEconomicSummary(Base):
    __tablename__ = "mart_economic_summary"
    __table_args__ = {"schema": "public_analytics"}

    series_id: Mapped[str] = mapped_column(String, primary_key=True)
    series_name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    latest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_value: Mapped[float | None] = mapped_column(Float, nullable=True)
