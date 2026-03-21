from datetime import date

from pydantic import BaseModel


class ObservationOut(BaseModel):
    observation_date: date
    value: float | None

    model_config = {"from_attributes": True}


class SeriesOut(BaseModel):
    series_id: str
    series_name: str
    source: str | None

    model_config = {"from_attributes": True}


class PaginatedSeriesOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SeriesOut]


class SeriesDetailOut(SeriesOut):
    observations: list[ObservationOut] = []


class InflationOut(BaseModel):
    series_id: str
    series_name: str
    source: str | None
    latest_date: date | None
    latest_value: float | None
    observations: list[ObservationOut] = []

    model_config = {"from_attributes": True}


class UnemploymentOut(BaseModel):
    series_id: str
    series_name: str
    source: str | None
    latest_date: date | None
    latest_value: float | None
    observations: list[ObservationOut] = []

    model_config = {"from_attributes": True}


class GdpOut(BaseModel):
    series_id: str
    series_name: str
    source: str | None
    latest_date: date | None
    latest_value: float | None
    observations: list[ObservationOut] = []

    model_config = {"from_attributes": True}


class KeyIndicator(BaseModel):
    series_id: str
    series_name: str
    source: str | None
    latest_date: date | None
    latest_value: float | None

    model_config = {"from_attributes": True}


class SummaryOut(BaseModel):
    indicators: list[KeyIndicator]
