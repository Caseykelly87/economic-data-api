"""Contract tests pinning the ETL -> API boundary.

The bundled parquets at ``app/fixtures/`` are byte-identical (verified by
SHA-256) with the ETL's canonical output at ``data/processed/canonical/`` —
the same artifacts the ETL's own ``test_sim_engine_contract.py`` exercises.
This file treats them as a fixed upstream contract and asserts that the
API's read/serve pipeline returns specific, independently-known values for
them.

A failure here means one of: the ETL changed its canonical output schema or
values, the API's read pipeline silently transformed a value, the schema
coercion regressed, or the documented response contract drifted from actual
behavior. Regenerating the fixtures and seeing a failure is the signal the
contract test exists to surface.

The ``client`` fixture overrides only the database dependency; the grocery
service is left live, so these tests run the real four-path resolution,
``pd.read_parquet`` call, schema coercion, and response shaping.
"""
import hashlib
from contextlib import ExitStack, contextmanager
from pathlib import Path
from shutil import copyfile
from unittest.mock import patch

import pytest

from app.core.config import settings

# Values below are read directly off the canonical parquets in app/fixtures/.
# store 1 on 2024-07-01 is the earliest store-day in store_daily_metrics.
KNOWN_STORE_ID = 1
KNOWN_DATE = "2024-07-01"
KNOWN_TOTAL_SALES = 86429.35
KNOWN_TRANSACTION_COUNT = 2337
DEPARTMENTS_PER_STORE = 10

# Maps each live-path setting to its canonical parquet filename.
CANONICAL_FILES = {
    "STORE_METRICS_PATH": "store_daily_metrics.parquet",
    "ANOMALY_FLAGS_PATH": "anomaly_flags.parquet",
    "DEPARTMENT_METRICS_PATH": "department_daily_metrics.parquet",
    "DIM_STORES_PATH": "dim_stores.parquet",
}

# SHA-256 of each bundled fixture, copied verbatim from the upstream ETL's
# data/processed/canonical/ output after the revenue_zscore_28d rule merge
# (economic-data-etl PR #25, merged 2026-05). These are the authoritative
# hashes for the contract — independently computed at the ETL boundary,
# pinned here so the test catches drift instead of co-computing both sides.
EXPECTED_FIXTURE_SHA256 = {
    "store_daily_metrics.parquet":
        "2ba24c7423ee7da2bccab3ba87765c77653c34955c565c9c66e1e49fa56b13a5",
    "department_daily_metrics.parquet":
        "bfe2a09525956d64c31fac91276140a433bd62466da837da78119ddd1be1f3ba",
    "dim_stores.parquet":
        "39ecd78ca98a23cafe57c7739755b250ae09ff32529459fae5440d61758e2125",
    "anomaly_flags.parquet":
        "f52a8d56b8a0e63fc8d1d0a5aff340795be88f05efa0db168fc204f20e6f8b0a",
}


@contextmanager
def _patched_settings(overrides):
    """Temporarily set the given attributes on the shared settings object."""
    with ExitStack() as stack:
        for name, value in overrides.items():
            stack.enter_context(patch.object(settings, name, value))
        yield


@pytest.mark.parametrize(
    "filename,expected_sha256",
    sorted(EXPECTED_FIXTURE_SHA256.items()),
)
def test_bundled_fixture_matches_canonical_sha256(filename, expected_sha256):
    """Each bundled parquet's SHA-256 matches the ETL canonical reference.

    Business-correctness: the assertion compares a freshly computed SHA-256
    of the bundled file against a hash captured independently at the ETL
    boundary, not against a re-hash of the same bytes. Drift in any
    direction — a stale fixture, a corrupted copy, an inadvertent
    re-encode — fails the test with the offending filename in the
    parametrize ID.
    """
    fixtures_dir = Path(settings.GROCERY_FIXTURES_DIR)
    fixture_path = fixtures_dir / filename
    assert fixture_path.is_file(), f"Fixture missing: {fixture_path}"
    actual_sha256 = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    assert actual_sha256 == expected_sha256, (
        f"{filename} drifted from ETL canonical. "
        f"Expected {expected_sha256}, got {actual_sha256}."
    )


def test_api_serves_canonical_store_day_values(client):
    """/store-metrics returns the exact canonical row for a known store-day."""
    resp = client.get(
        "/store-metrics",
        params={
            "start_date": KNOWN_DATE,
            "end_date": KNOWN_DATE,
            "store_id": KNOWN_STORE_ID,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    items = body["items"]
    assert len(items) == 1
    item = items[0]
    assert item["date"] == KNOWN_DATE
    assert item["store_id"] == KNOWN_STORE_ID
    assert item["total_sales"] == KNOWN_TOTAL_SALES
    assert item["transaction_count"] == KNOWN_TRANSACTION_COUNT


def test_api_cross_grain_reconciliation(client):
    """Department net_sales for a store-day sum to the store-day total_sales.

    The ETL's own contract test asserts this invariant on its transform
    output; the same invariant must survive the API's read/serve pipeline.
    The two endpoints read different canonical parquets at different grains,
    so agreement is a genuine cross-grain check, not a tautology.
    """
    dept = client.get(
        "/department-metrics",
        params={
            "start_date": KNOWN_DATE,
            "end_date": KNOWN_DATE,
            "store_id": KNOWN_STORE_ID,
            "limit": 200,
        },
    ).json()
    # The grain is store-day-department: ten departments per store-day.
    assert dept["total"] == DEPARTMENTS_PER_STORE
    dept_sum = round(sum(d["net_sales"] for d in dept["items"]), 2)

    store = client.get(
        "/store-metrics",
        params={
            "start_date": KNOWN_DATE,
            "end_date": KNOWN_DATE,
            "store_id": KNOWN_STORE_ID,
        },
    ).json()["items"][0]

    assert dept_sum == store["total_sales"] == KNOWN_TOTAL_SALES


def test_api_dim_stores_enforces_string_identifier_schema(client):
    """dim-stores serves zip and county_fips as zero-padded strings.

    The parquet stores both columns as int64; the service coerces them to
    5-character strings so identifiers with leading zeros round-trip and
    consumers treat them as identifiers, not numbers. This exercises that
    coercion against the real parquet — the route tests mock the service
    and so never run it.
    """
    rows = client.get("/dim-stores").json()
    assert len(rows) == 8
    by_id = {r["store_id"]: r for r in rows}

    store1 = by_id[1]
    assert isinstance(store1["zip"], str)
    assert store1["zip"] == "63122"
    assert isinstance(store1["county_fips"], str)
    assert store1["county_fips"] == "29189"
    # open_date is coerced from the parquet's string storage to a typed
    # date and serialized back as an ISO string.
    assert store1["open_date"] == "2009-04-15"

    # Every store's identifier strings are exactly five characters.
    for row in rows:
        assert isinstance(row["zip"], str) and len(row["zip"]) == 5
        assert isinstance(row["county_fips"], str) and len(row["county_fips"]) == 5


def test_offline_and_online_modes_serve_identical_output(client, tmp_path):
    """Both data-source modes return identical responses for identical input.

    Offline mode serves the bundled app/fixtures parquets. Online mode is
    simulated by copying those same parquets to a separate location and
    pointing the four ``*_PATH`` settings at the copies, which flips the
    four-path resolution onto its live branch. Same bytes underneath, so
    every endpoint must serve identical responses and /health must report
    the mode it is actually operating in.
    """
    fixtures_dir = Path(settings.GROCERY_FIXTURES_DIR)
    requests = [
        ("/store-metrics", {"limit": 50}),
        ("/department-metrics", {"limit": 50}),
        ("/anomalies", {"limit": 50}),
        ("/dim-stores", {}),
        ("/dashboard-summary", {"start_date": "2024-07-01", "end_date": "2025-12-31"}),
    ]

    # Offline mode: no *_PATH set, bundled fixtures served.
    assert settings.grocery_data_source == "fixtures"
    assert client.get("/health").json()["grocery_pipeline"]["mode"] == "offline"
    offline = {path: client.get(path, params=p).json() for path, p in requests}

    # Online mode: copy the canonical parquets out and resolve to the copies.
    overrides = {}
    for setting_name, filename in CANONICAL_FILES.items():
        dest = tmp_path / filename
        copyfile(fixtures_dir / filename, dest)
        overrides[setting_name] = str(dest)

    with _patched_settings(overrides):
        assert settings.grocery_data_source == "live"
        assert client.get("/health").json()["grocery_pipeline"]["mode"] == "online"
        online = {path: client.get(path, params=p).json() for path, p in requests}

    assert online == offline
