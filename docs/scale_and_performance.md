# Scale and Performance Decisions

## Purpose

This document records the deliberate small-data engineering choices in the
API service layer: why each is the right call at the current data volume,
the row count or condition where it would stop being the right call, and
what the replacement would be at that point. It exists so a reader can tell
the difference between code that is simple because the problem is small and
code that is simple because nobody thought about scale.

The honest caveat up front: I have not run this service under
production-scale load. The ceilings below are reasoned from how each pattern
grows with input size, not measured against a benchmark. Where I give a row
count, it is an order-of-magnitude judgment about where the pattern would
start to hurt, not a tested threshold.

## The data, in numbers

The canonical dataset the service reads, measured from the bundled
fixtures:

| Source                     | Rows   | Grain                                  |
|----------------------------|--------|----------------------------------------|
| `store_daily_metrics`      | 5,848  | 8 stores, 731 store-days each (2024-01 to 2025-12) |
| `department_daily_metrics` | 58,424 | store × department × day               |
| `anomaly_flags`            | 343    | one row per flagged store-day-rule     |
| `dim_stores`               | 8      | one row per store                      |

The macro side reads economic time series from Postgres; those fact tables
are in the low thousands of rows. Every working set here fits in memory many
times over. That fact is the premise behind each decision below.

## Decision 1 — Synchronous request handlers

**Decision.** The route layer uses synchronous `def` handlers, not
`async def`. The two `async def` functions in the app (the request-context
middleware `dispatch` and the global exception handler) are async only
because Starlette requires those hooks to be coroutines; no route handler is.

**Why it is right at this scale.** The handlers sit on top of a synchronous
database driver and synchronous parquet reads. FastAPI runs a `def` handler
in a threadpool, so a blocking call inside it does not block the event loop —
other requests keep being served while one handler waits on disk or the DB.
Writing `async def` over a blocking driver would be actively worse: the
blocking call would then run on the event loop thread and stall every other
in-flight request. Sync handlers over a sync data layer is the correct
pairing, not a shortcut.

**The ceiling.** This holds as long as the data layer is synchronous. If the
service moved to an async database driver (for example `asyncpg`) and an
async object store for the parquet reads, the handlers would migrate to
`async def` so they could `await` those calls directly and drop the
threadpool hop. The trigger is the data layer becoming async, not a row
count.

## Decision 2 — In-memory pandas

**Decision.** The grocery side loads each parquet file into a pandas
DataFrame and does its filtering, grouping, and aggregation in pandas.

**Why it is right at this scale.** Thousands to tens of thousands of rows is
squarely in pandas' comfort zone. The largest frame is the 58,424-row
department table; it loads and filters in milliseconds and the whole working
set fits in memory with room to spare. A query engine or a distributed
framework would add operational surface and a dependency footprint to solve
a problem this dataset does not have.

**The ceiling.** The constraint is single-machine memory. When a working set
grows past what fits comfortably in RAM — tens of gigabytes and up — the move
is a columnar query engine that reads only the columns and row groups a query
needs (DuckDB over the parquet files is the natural first step, since it
keeps the single-process model), and only past that, distributed processing.
None of that is warranted here, and adding it now would be complexity without
a problem to point it at.

## Decision 3 — Defensive `.copy()` on cached frames

**Decision.** The parquet loaders return `lru_cache`-wrapped DataFrames
shared across requests. Every service function that filters or sorts takes an
explicit `.copy()` of the cached frame before touching it.

**Why it is right at this scale.** The copy prevents a request from mutating
the shared cached object and corrupting it for every later request. At these
row counts the per-request copy is negligible — copying a few thousand rows
is far cheaper than the parquet read it avoids re-running, and it buys
correctness that is otherwise easy to lose to an accidental in-place
operation. The alternative — trusting every current and future call site to
never mutate the shared frame — is the kind of invariant that holds until
the one time it doesn't.

**The ceiling.** At very large frames the per-request copy would itself
become a cost worth removing. The replacement then is a read-only or
copy-on-write strategy: hand out a view and rely on pandas' copy-on-write
semantics, or restructure so consumers never need a mutable frame. That is a
real trade-off only once the frames are large enough for the copy to show up
in a request budget, which they are not here.

## Related

The ETL repo carries the same kind of annotation on its upsert path
(`economic-data-etl`, `src/load.py`), where the cost that scales is the
full-table read it does to diff against incoming rows. The fix named there —
a database-side `INSERT … ON CONFLICT … DO UPDATE` — is the load-side analogue
of the ceilings above: keep the simple version while the data is small, and
know exactly what replaces it when it isn't.
