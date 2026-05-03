"""Tests for the Prometheus /metrics endpoint and custom counters."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_200(self, client: TestClient):
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_endpoint_returns_prometheus_text_format(self, client: TestClient):
        response = client.get("/metrics")
        assert response.headers["content-type"].startswith("text/plain")
        body = response.text
        assert "# HELP" in body
        assert "# TYPE" in body

    def test_metrics_endpoint_includes_custom_counters(self, client: TestClient):
        client.get("/store-metrics?limit=2")
        client.get("/anomalies?limit=2")
        client.get(
            "/dashboard-summary?start_date=2025-07-01&end_date=2025-12-31"
        )

        response = client.get("/metrics")
        body = response.text

        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body

        assert "grocery_data_source_total" in body
        assert "service_call_total" in body
