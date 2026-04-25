"""
Tests for GET /metrics/inflation, /metrics/unemployment, and /metrics/gdp.

Service functions are patched so tests are isolated from the DB.
"""
from datetime import date
from unittest.mock import patch

from app.schemas.economic import GdpOut, InflationOut, ObservationOut, UnemploymentOut

SVC = "app.services.economic"

REQUIRED_METRIC_FIELDS = ("series_id", "series_name", "source", "latest_date", "latest_value", "observations")


def _obs() -> ObservationOut:
    return ObservationOut(observation_date=date(2024, 1, 1), value=3.1)


def _inflation(**kwargs) -> InflationOut:
    defaults = dict(
        series_id="CPIAUCSL", series_name="Consumer Price Index", source="BLS",
        latest_date=date(2024, 1, 1), latest_value=3.1, observations=[_obs()],
    )
    return InflationOut(**{**defaults, **kwargs})


def _unemployment(**kwargs) -> UnemploymentOut:
    defaults = dict(
        series_id="UNRATE", series_name="Unemployment Rate", source="BLS",
        latest_date=date(2024, 1, 1), latest_value=4.0, observations=[_obs()],
    )
    return UnemploymentOut(**{**defaults, **kwargs})


def _gdp(**kwargs) -> GdpOut:
    defaults = dict(
        series_id="GDPC1", series_name="GDP_REAL", source="FRED",
        latest_date=date(2025, 10, 1), latest_value=24065.955, observations=[_obs()],
    )
    return GdpOut(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# GET /metrics/inflation
# ---------------------------------------------------------------------------

def test_inflation_returns_200(client):
    with patch(f"{SVC}.get_inflation_series", return_value=[]):
        resp = client.get("/metrics/inflation")
    assert resp.status_code == 200


def test_inflation_returns_list(client):
    with patch(f"{SVC}.get_inflation_series", return_value=[_inflation()]):
        resp = client.get("/metrics/inflation")
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


def test_inflation_item_shape(client):
    with patch(f"{SVC}.get_inflation_series", return_value=[_inflation()]):
        resp = client.get("/metrics/inflation")
    item = resp.json()[0]
    for field in REQUIRED_METRIC_FIELDS:
        assert field in item, f"Missing field: {field}"


def test_inflation_date_filters_forwarded(client):
    with patch(f"{SVC}.get_inflation_series", return_value=[]) as mock:
        client.get("/metrics/inflation?start_date=2020-01-01&end_date=2023-12-31")
    _, kwargs = mock.call_args
    assert kwargs["start_date"] == date(2020, 1, 1)
    assert kwargs["end_date"] == date(2023, 12, 31)


def test_inflation_series_id_filter_forwarded(client):
    with patch(f"{SVC}.get_inflation_series", return_value=[]) as mock:
        client.get("/metrics/inflation?series_id=CPIAUCSL")
    _, kwargs = mock.call_args
    assert kwargs["series_id"] == "CPIAUCSL"


# ---------------------------------------------------------------------------
# GET /metrics/unemployment
# ---------------------------------------------------------------------------

def test_unemployment_returns_200(client):
    with patch(f"{SVC}.get_unemployment_series", return_value=[]):
        resp = client.get("/metrics/unemployment")
    assert resp.status_code == 200


def test_unemployment_returns_list(client):
    with patch(f"{SVC}.get_unemployment_series", return_value=[_unemployment()]):
        resp = client.get("/metrics/unemployment")
    assert len(resp.json()) == 1


def test_unemployment_item_shape(client):
    with patch(f"{SVC}.get_unemployment_series", return_value=[_unemployment()]):
        resp = client.get("/metrics/unemployment")
    item = resp.json()[0]
    for field in REQUIRED_METRIC_FIELDS:
        assert field in item, f"Missing field: {field}"


def test_unemployment_date_filters_forwarded(client):
    with patch(f"{SVC}.get_unemployment_series", return_value=[]) as mock:
        client.get("/metrics/unemployment?start_date=2021-01-01&series_id=UNRATE")
    _, kwargs = mock.call_args
    assert kwargs["start_date"] == date(2021, 1, 1)
    assert kwargs["series_id"] == "UNRATE"


# ---------------------------------------------------------------------------
# GET /metrics/gdp
# ---------------------------------------------------------------------------

def test_gdp_returns_200(client):
    with patch(f"{SVC}.get_gdp_series", return_value=[]):
        resp = client.get("/metrics/gdp")
    assert resp.status_code == 200


def test_gdp_returns_list(client):
    with patch(f"{SVC}.get_gdp_series", return_value=[_gdp()]):
        resp = client.get("/metrics/gdp")
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


def test_gdp_item_shape(client):
    with patch(f"{SVC}.get_gdp_series", return_value=[_gdp()]):
        resp = client.get("/metrics/gdp")
    item = resp.json()[0]
    for field in REQUIRED_METRIC_FIELDS:
        assert field in item, f"Missing field: {field}"


def test_gdp_date_filters_forwarded(client):
    with patch(f"{SVC}.get_gdp_series", return_value=[]) as mock:
        client.get("/metrics/gdp?start_date=2020-01-01&end_date=2025-01-01&series_id=GDPC1")
    _, kwargs = mock.call_args
    assert kwargs["start_date"] == date(2020, 1, 1)
    assert kwargs["end_date"] == date(2025, 1, 1)
    assert kwargs["series_id"] == "GDPC1"
