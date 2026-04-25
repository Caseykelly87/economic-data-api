"""Tests for GET /health — status check including DB connectivity."""


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_has_status_ok(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"


def test_health_response_has_version(client):
    data = client.get("/health").json()
    assert "version" in data


def test_health_response_has_db_field(client):
    data = client.get("/health").json()
    assert "db" in data


def test_health_db_connected_when_ping_succeeds(client):
    # Default MagicMock.execute() does not raise — DB is reachable.
    data = client.get("/health").json()
    assert data["db"] == "connected"


def test_health_returns_503_when_db_unavailable(client, mock_db):
    mock_db.execute.side_effect = Exception("Connection refused")
    resp = client.get("/health")
    assert resp.status_code == 503


def test_health_status_degraded_when_db_unavailable(client, mock_db):
    mock_db.execute.side_effect = Exception("Connection refused")
    data = client.get("/health").json()
    assert data["status"] == "degraded"
    assert data["db"] == "unavailable"
