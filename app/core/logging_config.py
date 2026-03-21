"""
Central logging configuration for the Economic Data API.

Call configure_logging() once at application startup. After that, any module
can obtain a logger with the standard ``logging.getLogger(__name__)`` pattern.
"""
import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """
    Configure the root logger with a timestamp + level + name format.

    Args:
        level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL (case-insensitive).
               Falls back to INFO for unrecognised values.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)-8s %(name)-35s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,  # override any handlers already attached (e.g. by uvicorn)
    )

    # SQLAlchemy logs every query at INFO; only surface warnings and above.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # Uvicorn's own access log duplicates our request middleware; silence it.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
