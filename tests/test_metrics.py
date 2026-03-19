from unittest.mock import MagicMock
from decimal import Decimal
from datetime import date

from app.models.economic import EconomicSeries, SeriesObservation


def _make_metric_series(series_id: str, name: str, category: str) -> EconomicSeries:
    obs = MagicMock(spec=SeriesObservation)
    obs.observation_date = date(2024, 1, 1)
    obs.value = Decimal("3.1")

    s = MagicMock(spec=EconomicSeries)
    s.series_id = series_id
    s.name = name
    s.category = category
    s.unit = "Percent"
    s.observations = [obs]
    return s


# --- GET /metrics/inflation ---

def test_inflation_returns_200(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    response = client.get("/metrics/inflation")
    assert response.status_code == 200


def test_inflation_returns_list(client, mock_db):
    series = _make_metric_series("CPIAUCSL", "Consumer Price Index", "inflation")
    mock_db.execute.return_value.scalars.return_value.all.return_value = [series]
    response = client.get("/metrics/inflation")
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1


def test_inflation_item_has_required_fields(client, mock_db):
    series = _make_metric_series("CPIAUCSL", "Consumer Price Index", "inflation")
    mock_db.execute.return_value.scalars.return_value.all.return_value = [series]
    response = client.get("/metrics/inflation")
    item = response.json()[0]
    assert "series_id" in item
    assert "name" in item
    assert "latest_date" in item
    assert "latest_value" in item
    assert "observations" in item


# --- GET /metrics/unemployment ---

def test_unemployment_returns_200(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    response = client.get("/metrics/unemployment")
    assert response.status_code == 200


def test_unemployment_returns_list(client, mock_db):
    series = _make_metric_series("UNRATE", "Unemployment Rate", "unemployment")
    mock_db.execute.return_value.scalars.return_value.all.return_value = [series]
    response = client.get("/metrics/unemployment")
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1


def test_unemployment_item_has_required_fields(client, mock_db):
    series = _make_metric_series("UNRATE", "Unemployment Rate", "unemployment")
    mock_db.execute.return_value.scalars.return_value.all.return_value = [series]
    response = client.get("/metrics/unemployment")
    item = response.json()[0]
    assert "series_id" in item
    assert "name" in item
    assert "latest_date" in item
    assert "latest_value" in item
    assert "observations" in item
