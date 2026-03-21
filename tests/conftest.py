import os

# Provide dummy DB config so Settings() doesn't fail during import in test environments.
for _var, _val in [("DB_HOST", "localhost"), ("DB_NAME", "test"), ("DB_USER", "test"), ("DB_PASSWORD", "test")]:
    os.environ.setdefault(_var, _val)

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def client(mock_db):
    """TestClient with DB dependency overridden by a controllable MagicMock session."""
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
