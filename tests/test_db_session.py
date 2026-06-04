"""Tests for app.db.session — the lazy engine/session lifecycle.

The SQLAlchemy engine is constructed lazily via ``get_engine()`` and
memoized, mirroring the lazy ``get_settings()`` convention in
app.core.config. Importing the module must not build a connection-pooled
engine as a side effect. These behaviors are pinned so a future change
cannot silently reintroduce import-time engine construction.
"""
from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import app.db.session as session_module


def test_import_does_not_construct_engine():
    """Business-correctness: reloading the module with create_engine
    patched proves no engine is built at import time. Against the prior
    eager code (a module-level ``engine = create_engine(...)``), the patch
    would fire during import and this assertion would fail; with lazy
    construction create_engine is never called until get_engine() runs.
    The finally-clause reload restores the module's real create_engine
    binding for any later test."""
    try:
        with patch("sqlalchemy.create_engine") as mock_create_engine:
            importlib.reload(session_module)
            mock_create_engine.assert_not_called()
    finally:
        importlib.reload(session_module)


def test_get_engine_is_memoized():
    """Business-correctness: the lru_cache wrapper must return the same
    Engine instance on subsequent calls, mirroring test_get_settings_is_cached.
    create_engine builds the Engine object without opening a connection,
    so calling it is safe against the dummy test DB config."""
    assert session_module.get_engine() is session_module.get_engine()


def test_get_db_yields_and_closes_session():
    """Business-correctness: get_db yields the session produced by the lazy
    sessionmaker and closes it in the finally block. The sessionmaker is
    patched so no real connection is attempted; the test pins the exact
    yield-then-close contract that the FastAPI dependency relies on."""
    fake_session = MagicMock()
    fake_maker = MagicMock(return_value=fake_session)
    with patch.object(session_module, "get_sessionmaker", return_value=fake_maker):
        gen = session_module.get_db()
        yielded = next(gen)
        assert yielded is fake_session
        fake_session.close.assert_not_called()
        gen.close()  # raises GeneratorExit at the yield, running the finally
        fake_session.close.assert_called_once()
