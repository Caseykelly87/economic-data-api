"""
Central logging configuration for the Economic Data API.

Call configure_logging() once at application startup. Modules can then
obtain a structlog logger with structlog.get_logger(__name__), or use
the standard logging.getLogger(__name__) pattern - both flow through
the same renderer and level filter via the stdlib bridge.

Output format
-------------
- Auto-detect: console (colored, human-friendly) when stdout is a tty,
  json (single-line, machine-parseable) otherwise.
- Override: set LOG_FORMAT=json or LOG_FORMAT=console.

Log level
---------
Resolution order:
1. The level argument to configure_logging(), if provided.
2. The LOG_LEVEL environment variable.
3. INFO default.

Valid values (case-insensitive): debug, info, warning, error, critical.

Windows note
------------
Stdout is reconfigured to utf-8 with errors="replace" so non-ASCII
characters in log strings don't crash on Windows when output is piped
or redirected.
"""

from __future__ import annotations

import logging
import os
import sys

import structlog


def _resolve_level(level_arg: str | None) -> int:
    """Resolution order: arg > env > default."""
    if level_arg is not None:
        raw = level_arg
    else:
        raw = os.environ.get("LOG_LEVEL", "INFO")
    mapping = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    return mapping.get(raw.lower(), logging.INFO)


def _resolve_format() -> str:
    raw = os.environ.get("LOG_FORMAT", "").lower()
    if raw in ("json", "console"):
        return raw
    return "console" if sys.stdout.isatty() else "json"


def _add_logger_name_safe(logger, method_name, event_dict):
    """Tolerant of loggers without a .name attribute (e.g. PrintLogger)."""
    name = getattr(logger, "name", None)
    if name is not None:
        event_dict["logger"] = name
    return event_dict


def configure_logging(level: str | None = "INFO") -> None:
    """
    Configure structlog and the stdlib logging bridge.

    Args:
        level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL (case-insensitive).
               If None, the LOG_LEVEL env var is consulted, falling back to
               INFO. The default of "INFO" preserves the original signature
               so existing callers work unchanged.

    Idempotent - calling twice is safe.
    """
    # Windows cp1252 fix: reconfigure stdout to utf-8 so non-ASCII
    # characters don't crash when output is piped or redirected.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    numeric_level = _resolve_level(level)
    output_format = _resolve_format()

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors = [
        # contextvars must come first so request_id and other bound
        # values appear on every log line emitted during the request
        # lifetime
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        _add_logger_name_safe,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if output_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib logging through structlog so existing
    # logging.getLogger(__name__) usage gets the same output.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=shared_processors,
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(numeric_level)

    # SQLAlchemy logs every query at INFO; surface only warnings and above.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # Uvicorn's own access log duplicates the request middleware; silence it.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
