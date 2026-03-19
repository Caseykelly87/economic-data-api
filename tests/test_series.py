from unittest.mock import MagicMock
from decimal import Decimal
from datetime import date

from app.models.economic import EconomicSeries, SeriesObservation


def _make_series(**kwargs) -> EconomicSeries:
    defaults = dict(
        id=1,
        series_id="CPIAUCSL",
        name="Consumer Price Index",
        description="CPI for all urban consumers",
        category="inflation",
        unit="Index 1982-84=100",
        frequency="monthly",
        observations=[],
    )
    defaults.update(kwargs)
    s = MagicMock(spec=EconomicSeries)
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


def _make_observation(obs_date: date, value: Decimal) -> SeriesObservation:
    o = MagicMock(spec=SeriesObservation)
    o.observation_date = obs_date
    o.value = value
    return o


# --- GET /series ---

def test_list_series_returns_200(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    response = client.get("/series")
    assert response.status_code == 200


def test_list_series_returns_list(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [
        _make_series(),
        _make_series(id=2, series_id="UNRATE", name="Unemployment Rate"),
    ]
    response = client.get("/series")
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2


def test_list_series_item_shape(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_series()]
    response = client.get("/series")
    item = response.json()[0]
    assert item["series_id"] == "CPIAUCSL"
    assert item["name"] == "Consumer Price Index"
    assert "description" in item
    assert "category" in item
    assert "unit" in item
    assert "frequency" in item


# --- GET /series/{series_id} ---

def test_get_series_returns_200(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.first.return_value = _make_series()
    response = client.get("/series/CPIAUCSL")
    assert response.status_code == 200


def test_get_series_response_shape(client, mock_db):
    obs = _make_observation(date(2024, 1, 1), Decimal("310.326"))
    series = _make_series(observations=[obs])
    mock_db.execute.return_value.scalars.return_value.first.return_value = series
    response = client.get("/series/CPIAUCSL")
    data = response.json()
    assert data["series_id"] == "CPIAUCSL"
    assert "observations" in data
    assert isinstance(data["observations"], list)


def test_get_series_observation_shape(client, mock_db):
    obs = _make_observation(date(2024, 1, 1), Decimal("310.326"))
    series = _make_series(observations=[obs])
    mock_db.execute.return_value.scalars.return_value.first.return_value = series
    response = client.get("/series/CPIAUCSL")
    observation = response.json()["observations"][0]
    assert "observation_date" in observation
    assert "value" in observation


def test_get_series_not_found_returns_404(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.first.return_value = None
    response = client.get("/series/NONEXISTENT")
    assert response.status_code == 404
