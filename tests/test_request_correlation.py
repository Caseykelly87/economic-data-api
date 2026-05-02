"""Tests for the request correlation middleware in app/main.py.

Reuses the ``client`` fixture from tests/conftest.py, which overrides
the DB dependency with a MagicMock so /health doesn't try to reach a
real database.
"""

from __future__ import annotations

import re
import uuid


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class TestRequestCorrelation:
    def test_response_includes_x_request_id_header(self, client):
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        assert UUID_PATTERN.match(response.headers["X-Request-ID"])

    def test_incoming_x_request_id_is_echoed_back(self, client):
        provided_id = str(uuid.uuid4())
        response = client.get("/health", headers={"X-Request-ID": provided_id})
        assert response.headers["X-Request-ID"] == provided_id

    def test_each_request_gets_a_unique_id_when_no_header_provided(self, client):
        r1 = client.get("/health")
        r2 = client.get("/health")
        assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]
