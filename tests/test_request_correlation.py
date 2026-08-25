"""Tests for the request correlation middleware in app/main.py.

Reuses the ``client`` fixture from tests/conftest.py, which overrides
the DB dependency with a MagicMock so /health doesn't try to reach a
real database.
"""

from __future__ import annotations

import re
import uuid

from app.main import _validate_request_id

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


class TestRequestIdValidation:
    """Business-correctness: the middleware must reject attacker-controlled
    X-Request-ID inputs (oversized or malformed) and replace them with a
    freshly generated UUID, without echoing the rejected input. The four
    tests below pin the four input shapes the validator must distinguish.
    """

    def test_x_request_id_valid_uuid_is_echoed_unchanged(self, client):
        provided_id = str(uuid.uuid4())
        response = client.get("/health", headers={"X-Request-ID": provided_id})
        assert response.headers["X-Request-ID"] == provided_id

    def test_x_request_id_oversized_input_generates_new_uuid(self, client):
        oversized = "a" * 10_000
        response = client.get("/health", headers={"X-Request-ID": oversized})
        echoed = response.headers["X-Request-ID"]
        assert echoed != oversized
        assert UUID_PATTERN.match(echoed)

    def test_x_request_id_malformed_input_generates_new_uuid(self, client):
        response = client.get("/health", headers={"X-Request-ID": "not-a-uuid"})
        echoed = response.headers["X-Request-ID"]
        assert echoed != "not-a-uuid"
        assert UUID_PATTERN.match(echoed)

    def test_x_request_id_absent_generates_new_uuid(self, client):
        response = client.get("/health")
        assert UUID_PATTERN.match(response.headers["X-Request-ID"])


class TestValidateRequestIdHelper:
    """Direct unit tests for the helper, independent of the middleware."""

    def test_returns_input_when_canonical_uuid(self):
        provided = str(uuid.uuid4())
        assert _validate_request_id(provided) == provided

    def test_returns_fresh_uuid_when_none(self):
        result = _validate_request_id(None)
        assert UUID_PATTERN.match(result)

    def test_returns_fresh_uuid_when_oversized(self):
        result = _validate_request_id("a" * 10_000)
        assert UUID_PATTERN.match(result)

    def test_returns_fresh_uuid_when_uppercase(self):
        # The canonical form is lowercase; uppercase hex is not accepted.
        upper = str(uuid.uuid4()).upper()
        result = _validate_request_id(upper)
        assert result != upper
        assert UUID_PATTERN.match(result)

    def test_returns_fresh_uuid_when_37_char_with_trailing_garbage(self):
        # Exactly one character over the cap, with valid UUID prefix; rejected.
        provided = str(uuid.uuid4()) + "x"
        result = _validate_request_id(provided)
        assert result != provided
        assert UUID_PATTERN.match(result)
