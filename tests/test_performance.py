"""Performance / load tests for the read endpoints.

These are regression guards against catastrophic slowdown (a deadlock, an
accidental O(n^2) rewrite, a per-request cache miss), not microbenchmarks.
Every wall-clock bound is deliberately loose: it is several times the time
the batch takes locally, so the test fails on a real regression but not on
a slow shared CI runner. Where a timing assertion could not be made both
meaningful and stable, the test leans on an invariant instead (all 200,
exact row count, single disk read).

The concurrency here is genuine: FastAPI runs the synchronous route
handlers in a threadpool, so firing many requests through one TestClient
exercises real simultaneous execution of the parquet-backed read path that
the scale-and-performance decision record reasons about.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pandas as pd

from app.services import grocery as svc

# The store-metrics pagination cap (limit le=200) and the canonical
# store_daily_metrics row count. Both are fixed by the route/Query bound
# and the bundled fixture, not by anything these tests do.
PAGE_SIZE_CAP = 200
STORE_METRICS_TOTAL = 5848


def test_concurrent_reads_all_succeed_within_bound(client):
    """Business-correctness-adjacent: 100 concurrent /store-metrics reads
    must all return 200 and the batch must finish well inside a generous
    wall-clock bound. The invariant (every request 200, none dropped or
    deadlocked) is the real assertion; the 30s bound is a coarse guard
    against a hang or a catastrophic slowdown, set at roughly 6x the local
    batch time so a slow CI runner does not flake it."""
    n = 100
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        responses = list(
            pool.map(lambda _: client.get("/store-metrics?limit=50"), range(n))
        )
    elapsed = time.perf_counter() - start

    assert len(responses) == n
    assert all(r.status_code == 200 for r in responses)
    # Every response carries the same full total; concurrent access must not
    # corrupt the shared cached frame into a partial count.
    assert all(r.json()["total"] == STORE_METRICS_TOTAL for r in responses)
    assert elapsed < 30.0, f"100 concurrent reads took {elapsed:.2f}s (bound 30s)"


def test_largest_payload_returns_full_page_within_bound(client):
    """Business-correctness-adjacent: requesting the pagination cap
    (limit=200) returns exactly 200 items and the full total, exercising
    the largest response the API can emit in one page. The 10s bound on a
    single request has wide headroom (the read is milliseconds locally);
    the meaningful assertions are the exact item count and total."""
    start = time.perf_counter()
    resp = client.get(f"/store-metrics?limit={PAGE_SIZE_CAP}")
    elapsed = time.perf_counter() - start

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == STORE_METRICS_TOTAL
    assert body["limit"] == PAGE_SIZE_CAP
    assert len(body["items"]) == PAGE_SIZE_CAP
    assert elapsed < 10.0, f"largest-page request took {elapsed:.2f}s (bound 10s)"


def test_repeated_reads_hit_cache_single_disk_read(client):
    """Business-correctness: the lru_cache on the parquet loaders means
    repeated requests to a cached endpoint read the file from disk once,
    not once per request. Asserting pd.read_parquet is called exactly once
    across 20 sequential /store-metrics requests ties directly to the
    cache claim in the scale-and-performance decision record. The cache is
    cleared first so the count starts from a known-cold state."""
    svc._clear_grocery_caches()
    with patch(
        "app.services.grocery.pd.read_parquet", wraps=pd.read_parquet
    ) as mock_read:
        for _ in range(20):
            resp = client.get("/store-metrics?limit=10")
            assert resp.status_code == 200
        # /store-metrics reads only store_daily_metrics; the first request
        # loads it, every later request is served from the lru_cache.
        assert mock_read.call_count == 1
