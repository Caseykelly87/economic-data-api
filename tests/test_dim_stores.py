"""Tests for GET /dim-stores.

Service is patched so tests are isolated from parquet io.
"""
from datetime import date
from unittest.mock import patch

from app.schemas.grocery import StoreDimensionOut

SVC = "app.services.grocery"

REQUIRED_ITEM_FIELDS = (
    "store_id", "store_name", "address", "city",
    "zip", "county_fips", "trade_area_profile",
    "sqft", "open_date", "base_daily_revenue",
)


def _row(**kwargs) -> StoreDimensionOut:
    defaults = dict(
        store_id=1,
        store_name="Knot Shore Kirkwood",
        address="123 Main St",
        city="Kirkwood",
        zip="63122",
        county_fips="29189",
        trade_area_profile="suburban-family",
        sqft=42000,
        open_date=date(2018, 6, 1),
        base_daily_revenue=63500.0,
    )
    return StoreDimensionOut(**{**defaults, **kwargs})


def test_dim_stores_returns_200_empty(client):
    with patch(f"{SVC}.get_dim_stores", return_value=[]):
        resp = client.get("/dim-stores")
    assert resp.status_code == 200
    assert resp.json() == []


def test_dim_stores_returns_flat_array(client):
    with patch(f"{SVC}.get_dim_stores", return_value=[_row()]):
        resp = client.get("/dim-stores")
    assert resp.status_code == 200
    body = resp.json()
    # Flat array, not envelope
    assert isinstance(body, list)
    assert len(body) == 1


def test_dim_stores_item_shape(client):
    with patch(f"{SVC}.get_dim_stores", return_value=[_row()]):
        resp = client.get("/dim-stores")
    assert resp.status_code == 200
    item = resp.json()[0]
    for field in REQUIRED_ITEM_FIELDS:
        assert field in item, f"missing item field: {field}"


def test_dim_stores_zip_is_string(client):
    """zip must be a string in the json response, not an integer."""
    with patch(f"{SVC}.get_dim_stores", return_value=[_row(zip="63122")]):
        resp = client.get("/dim-stores")
    item = resp.json()[0]
    assert isinstance(item["zip"], str)
    assert item["zip"] == "63122"


def test_dim_stores_county_fips_is_string(client):
    """county_fips must be a string in the json response, not an integer."""
    with patch(f"{SVC}.get_dim_stores", return_value=[_row(county_fips="29189")]):
        resp = client.get("/dim-stores")
    item = resp.json()[0]
    assert isinstance(item["county_fips"], str)
    assert item["county_fips"] == "29189"


def test_dim_stores_open_date_is_iso_string(client):
    """open_date is serialized as iso string (FastAPI default for date types)."""
    with patch(f"{SVC}.get_dim_stores", return_value=[_row(open_date=date(2018, 6, 1))]):
        resp = client.get("/dim-stores")
    item = resp.json()[0]
    assert item["open_date"] == "2018-06-01"


def test_dim_stores_no_pagination_query_params(client):
    """The endpoint accepts no query parameters; passing limit/offset is silently ignored."""
    with patch(f"{SVC}.get_dim_stores", return_value=[_row()]) as m:
        resp = client.get("/dim-stores", params={"limit": 5, "offset": 10})
    assert resp.status_code == 200
    # Service called with no arguments
    m.assert_called_once_with()
