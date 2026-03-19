from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ObservationOut(BaseModel):
    observation_date: date
    value: Decimal | None

    model_config = {"from_attributes": True}


class SeriesOut(BaseModel):
    series_id: str
    name: str
    description: str | None
    category: str | None
    unit: str | None
    frequency: str | None

    model_config = {"from_attributes": True}


class SeriesDetailOut(SeriesOut):
    observations: list[ObservationOut] = []


class InflationOut(BaseModel):
    series_id: str
    name: str
    unit: str | None
    latest_date: date | None
    latest_value: Decimal | None
    observations: list[ObservationOut] = []

    model_config = {"from_attributes": True}


class UnemploymentOut(BaseModel):
    series_id: str
    name: str
    unit: str | None
    latest_date: date | None
    latest_value: Decimal | None
    observations: list[ObservationOut] = []

    model_config = {"from_attributes": True}


class KeyIndicator(BaseModel):
    series_id: str
    name: str
    unit: str | None
    latest_date: date | None
    latest_value: Decimal | None

    model_config = {"from_attributes": True}


class SummaryOut(BaseModel):
    indicators: list[KeyIndicator]
