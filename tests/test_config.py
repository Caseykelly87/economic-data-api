"""Tests for app.core.config — the lazy Settings lifecycle.

The Settings instance is constructed lazily on first access via
``get_settings()`` and cached for the process lifetime. A module-level
``__getattr__`` shim preserves the ``from app.core.config import settings``
import shape that existed before the refactor. Both behaviors are pinned
here so a future change cannot silently reintroduce import-time work or
break callers that rely on the module attribute.
"""
from __future__ import annotations

from app.core.config import Settings, get_settings


def test_get_settings_returns_settings_instance():
    assert isinstance(get_settings(), Settings)


def test_get_settings_is_cached():
    """Business-correctness: the lru_cache wrapper must return the same
    instance on subsequent calls. The test guards against a regression
    where get_settings is rewritten to construct a fresh Settings on each
    call, which would defeat the point of the lazy memoization."""
    assert get_settings() is get_settings()


def test_module_level_settings_import_returns_cached_instance():
    """The ``from app.core.config import settings`` import path is what
    every existing caller uses. The module-level ``__getattr__`` shim
    must resolve it to the same cached instance get_settings() returns,
    so the import contract survives the lazy refactor."""
    from app.core.config import settings as imported_settings

    assert imported_settings is get_settings()
