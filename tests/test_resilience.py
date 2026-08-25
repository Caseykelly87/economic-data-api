"""Destructive / fault-injection tests for the read endpoints.

These are distinct from the input-validation suite (the existing
`_returns_422/400/404` tests, which confirm bad input is rejected at the
edge). Here the input is valid; what is abnormal is the runtime condition:
the data source failing mid-request, many requests hitting the shared
cached frames at once, and repeated traffic at the pagination cap
boundary. The assertion in each case is that the service degrades cleanly
(a clean 5xx envelope, correct per-request results, no 500, no hang),
which is the resilience property the validation tests do not touch.
"""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

# store_daily_metrics canaries: full row count and the per-store count
# used to check that concurrent filtered reads stay correct. 5848 rows /
# 8 stores = 731 store-days each.
STORE_METRICS_TOTAL = 5848
PER_STORE_ROWS = 731
OFFSET_CAP = 100_000
PAGE_SIZE_CAP = 200


def test_data_source_failure_returns_clean_500(client):
    """Business-correctness: when the parquet loader raises mid-request
    (disk gone, corrupt file, permission flip), the global exception
    handler must convert it to a 500 carrying the fixed error envelope —
    not propagate the traceback into the response body and not hang. A
    local client with raise_server_exceptions=False is used so the HTTP
    response the client would actually see is asserted, rather than the
    re-raised exception."""
    with patch(
        "app.services.grocery.load_store_metrics_df",
        side_effect=RuntimeError("parquet read failed mid-request"),
    ):
        with TestClient(app, raise_server_exceptions=False) as safe_client:
            resp = safe_client.get("/store-metrics?limit=10")

    assert resp.status_code == 500
    # The handler returns a fixed envelope; the underlying exception text
    # ("parquet read failed mid-request") must not leak to the caller.
    assert resp.json() == {"detail": "An internal server error occurred."}
    assert "parquet read failed" not in resp.text


def test_concurrent_filtered_reads_stay_correct(client):
    """Business-correctness: each grocery service takes a defensive
    .copy() of the shared lru_cached frame before filtering. Firing many
    concurrent store-filtered reads must therefore return only the
    requested store's rows in every response — a request must never see
    another request's filter bleed through. This is the concurrency guard
    on the .copy() pattern the scale-and-performance record documents."""
    store_ids = [1, 2, 3, 4, 5, 6, 7, 8] * 8  # 64 concurrent requests

    def fetch(store_id):
        resp = client.get(f"/store-metrics?store_id={store_id}&limit={PAGE_SIZE_CAP}")
        return store_id, resp

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(fetch, store_ids))

    for store_id, resp in results:
        assert resp.status_code == 200
        body = resp.json()
        # Each store has the full 731-day history; the filtered total must
        # be exactly that, never the unfiltered 5848 (which would mean the
        # filter was lost to a shared-frame race).
        assert body["total"] == PER_STORE_ROWS
        assert all(item["store_id"] == store_id for item in body["items"])


def test_boundary_pagination_under_load(client):
    """Business-correctness: the offset/limit caps (offset=100000,
    limit=200) are valid input, distinct from the single-shot
    over-cap 422 test. Hammered concurrently they must stay stable: the
    at-cap offset returns an empty page with the full total and 200, the
    at-cap limit returns a full 200-item page, and nothing 500s or hangs."""

    def fetch(kind):
        if kind == "offset_cap":
            return kind, client.get(f"/store-metrics?offset={OFFSET_CAP}&limit=50")
        return kind, client.get(f"/store-metrics?limit={PAGE_SIZE_CAP}")

    kinds = (["offset_cap", "limit_cap"] * 25)  # 50 concurrent boundary hits

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(fetch, kinds))

    for kind, resp in results:
        assert resp.status_code == 200, f"{kind} returned {resp.status_code}"
        body = resp.json()
        # The total is the full row count regardless of where the page
        # window sits; the cap offset lands past the last row.
        assert body["total"] == STORE_METRICS_TOTAL
        if kind == "offset_cap":
            assert body["offset"] == OFFSET_CAP
            assert body["items"] == []
        else:
            assert len(body["items"]) == PAGE_SIZE_CAP
