"""
Custom Prometheus counters for the API.

The HTTP request triplet (http_requests_total, http_request_duration_seconds,
http_requests_inprogress) is auto-instrumented by
prometheus-fastapi-instrumentator and does not need custom definitions.

The custom counters here track operational facts that are interesting in
aggregate but aren't naturally captured as HTTP-level metrics:

- grocery_data_source_total: how often grocery requests serve fixtures vs
  live data. Helps operators confirm production is using live data and
  spot misconfiguration where a deployed instance falls back to fixtures.

- service_call_total: how often each grocery service function is invoked.
  Pairs with the service_call_started/service_call_completed log events
  emitted at the same call sites; the log events give per-call detail,
  the counter gives aggregate rates.

Counters are imported and incremented from the grocery service layer.
"""

from __future__ import annotations

from prometheus_client import Counter


grocery_data_source_total = Counter(
    "grocery_data_source_total",
    "Number of grocery requests served, labeled by data source.",
    labelnames=["source"],
)

service_call_total = Counter(
    "service_call_total",
    "Number of grocery service function calls, labeled by service name.",
    labelnames=["service"],
)
