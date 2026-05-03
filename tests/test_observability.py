"""Tests for the structlog configurator in app/core/logging_config.py."""

from __future__ import annotations

import io
import json
import logging
import os
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest
import structlog

from app.core.logging_config import configure_logging


@pytest.fixture(autouse=True)
def reset_structlog():
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


class TestConfigureLogging:
    def test_default_invocation_runs_without_error(self):
        configure_logging()

    def test_explicit_level_arg_takes_precedence(self):
        # Function arg overrides env var
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}, clear=False):
            configure_logging(level="WARNING")
            buf = io.StringIO()
            with redirect_stdout(buf):
                logger = structlog.get_logger("test")
                logger.info("info_message")     # filtered (level=warning)
                logger.warning("warn_message")  # passes
            assert "info_message" not in buf.getvalue()
            assert "warn_message" in buf.getvalue()

    def test_json_format_emits_parseable_json(self):
        with patch.dict(os.environ, {"LOG_FORMAT": "json"}, clear=False):
            configure_logging()
            buf = io.StringIO()
            with redirect_stdout(buf):
                logger = structlog.get_logger("test")
                logger.info("test_event", endpoint="/store-metrics", duration_ms=12.4)
            line = buf.getvalue().strip().split("\n")[-1]
            payload = json.loads(line)
            assert payload["event"] == "test_event"
            assert payload["endpoint"] == "/store-metrics"
            assert payload["duration_ms"] == 12.4
            assert "timestamp" in payload
            assert payload["level"] == "info"

    def test_stdlib_extra_kwarg_fields_appear_in_output(self):
        """Verify the stdlib bridge propagates extra={} fields to the renderer.

        Without structlog.stdlib.ExtraAdder() in the shared processor chain,
        ProcessorFormatter silently drops attributes injected via extra={};
        the rendered output omits them. This test guards against that
        regression.
        """
        import logging as stdlib_logging

        with patch.dict(os.environ, {"LOG_FORMAT": "json"}, clear=False):
            buf = io.StringIO()
            with redirect_stdout(buf):
                # configure_logging must run while sys.stdout is buf because
                # the stdlib bridge's StreamHandler captures sys.stdout at
                # init time, unlike structlog's PrintLogger which resolves
                # it lazily. Without this ordering, the handler keeps writing
                # to the real stdout and buf stays empty.
                configure_logging()
                stdlib_logging.info(
                    "extra_kwarg_test",
                    extra={"endpoint": "/store-metrics", "duration_ms": 12.4, "row_count": 42},
                )
            line = buf.getvalue().strip().split("\n")[-1]
            assert line, "expected at least one line of json output"
            payload = json.loads(line)
            assert payload["event"] == "extra_kwarg_test"
            assert payload["endpoint"] == "/store-metrics"
            assert payload["duration_ms"] == 12.4
            assert payload["row_count"] == 42
            assert payload["level"] == "info"
