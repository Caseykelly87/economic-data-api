from unittest.mock import MagicMock
from decimal import Decimal
from datetime import date

from app.models.economic import EconomicSeries, SeriesObservation


def _make_series_with_obs(series_id: str, name: str) -> EconomicSeries:
    obs = MagicMock(spec=SeriesObservation)
    obs.observation_date = date(2024, 1, 1)
    obs.value = Decimal("5.0")

    s = MagicMock(spec=EconomicSeries)
    s.series_id = series_id
    s.name = name
    s.unit = "Percent"
    s.observations = [obs]
    return s


# --- GET /insights/summary ---

def test_summary_returns_200(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    response = client.get("/insights/summary")
    assert response.status_code == 200


def test_summary_response_has_indicators_key(client, mock_db):
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    response = client.get("/insights/summary")
    data = response.json()
    assert "indicators" in data
    assert isinstance(data["indicators"], list)


def test_summary_indicator_shape(client, mock_db):
    series = _make_series_with_obs("CPIAUCSL", "Consumer Price Index")
    mock_db.execute.return_value.scalars.return_value.all.return_value = [series]
    response = client.get("/insights/summary")
    indicators = response.json()["indicators"]
    assert len(indicators) == 1
    item = indicators[0]
    assert "series_id" in item
    assert "name" in item
    assert "unit" in item
    assert "latest_date" in item
    assert "latest_value" in item


def test_summary_latest_value_is_most_recent(client, mock_db):
    obs1 = MagicMock(spec=SeriesObservation)
    obs1.observation_date = date(2023, 1, 1)
    obs1.value = Decimal("3.0")

    obs2 = MagicMock(spec=SeriesObservation)
    obs2.observation_date = date(2024, 6, 1)
    obs2.value = Decimal("3.5")

    s = MagicMock(spec=EconomicSeries)
    s.series_id = "CPIAUCSL"
    s.name = "Consumer Price Index"
    s.unit = "Index"
    s.observations = [obs1, obs2]

    mock_db.execute.return_value.scalars.return_value.all.return_value = [s]
    response = client.get("/insights/summary")
    item = response.json()["indicators"][0]
    assert item["latest_date"] == "2024-06-01"
    assert float(item["latest_value"]) == 3.5
