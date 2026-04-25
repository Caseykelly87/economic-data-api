"""
Tests for GET /series and GET /series/{series_id}.

Service functions are patched so tests are isolated from the DB.
"""
from datetime import date
from unittest.mock import patch

from app.schemas.economic import ObservationOut, PaginatedSeriesOut, SeriesDetailOut, SeriesOut

SVC = "app.services.economic"


def _series(**kwargs) -> SeriesOut:
    defaults = dict(series_id="CPIAUCSL", series_name="Consumer Price Index", source="BLS")
    return SeriesOut(**{**defaults, **kwargs})


def _obs(d: date = date(2024, 1, 1), v: float = 310.3) -> ObservationOut:
    return ObservationOut(observation_date=d, value=v)


def _detail(**kwargs) -> SeriesDetailOut:
    defaults = dict(series_id="CPIAUCSL", series_name="Consumer Price Index", source="BLS", observations=[])
    return SeriesDetailOut(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# GET /series — list with pagination
# ---------------------------------------------------------------------------

def test_list_series_returns_200(client):
    with patch(f"{SVC}.get_all_series", return_value=(0, [])):
        resp = client.get("/series")
    assert resp.status_code == 200


def test_list_series_returns_paginated_shape(client):
    with patch(f"{SVC}.get_all_series", return_value=(1, [_series()])):
        resp = client.get("/series")
    data = resp.json()
    assert data["total"] == 1
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert len(data["items"]) == 1


def test_list_series_item_shape(client):
    with patch(f"{SVC}.get_all_series", return_value=(1, [_series()])):
        resp = client.get("/series")
    item = resp.json()["items"][0]
    assert item["series_id"] == "CPIAUCSL"
    assert item["series_name"] == "Consumer Price Index"
    assert "source" in item


def test_list_series_pagination_params_forwarded(client):
    with patch(f"{SVC}.get_all_series", return_value=(0, [])) as mock:
        client.get("/series?limit=10&offset=20")
    _, kwargs = mock.call_args
    assert kwargs["limit"] == 10
    assert kwargs["offset"] == 20


def test_list_series_limit_zero_returns_422(client):
    resp = client.get("/series?limit=0")
    assert resp.status_code == 422


def test_list_series_limit_too_large_returns_422(client):
    resp = client.get("/series?limit=201")
    assert resp.status_code == 422


def test_list_series_negative_offset_returns_422(client):
    resp = client.get("/series?offset=-1")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /series/{series_id}
# ---------------------------------------------------------------------------

def test_get_series_returns_200(client):
    with patch(f"{SVC}.get_series_by_id", return_value=_detail()):
        resp = client.get("/series/CPIAUCSL")
    assert resp.status_code == 200


def test_get_series_response_shape(client):
    obs = _obs()
    with patch(f"{SVC}.get_series_by_id", return_value=_detail(observations=[obs])):
        resp = client.get("/series/CPIAUCSL")
    data = resp.json()
    assert data["series_id"] == "CPIAUCSL"
    assert "observations" in data
    assert len(data["observations"]) == 1


def test_get_series_observation_shape(client):
    with patch(f"{SVC}.get_series_by_id", return_value=_detail(observations=[_obs()])):
        resp = client.get("/series/CPIAUCSL")
    obs = resp.json()["observations"][0]
    assert "observation_date" in obs
    assert "value" in obs


def test_get_series_not_found_returns_404(client):
    with patch(f"{SVC}.get_series_by_id", return_value=None):
        resp = client.get("/series/NONEXISTENT")
    assert resp.status_code == 404


def test_get_series_date_filters_forwarded(client):
    with patch(f"{SVC}.get_series_by_id", return_value=_detail()) as mock:
        client.get("/series/CPIAUCSL?start_date=2020-01-01&end_date=2023-12-31")
    _, kwargs = mock.call_args
    assert kwargs["start_date"] == date(2020, 1, 1)
    assert kwargs["end_date"] == date(2023, 12, 31)


def test_get_series_invalid_date_returns_422(client):
    resp = client.get("/series/CPIAUCSL?start_date=not-a-date")
    assert resp.status_code == 422
