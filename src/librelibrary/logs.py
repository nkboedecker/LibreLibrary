"""Structured logs, written to stderr."""

import logging
import sys

import structlog


def configure_logging() -> None:
    """Send JSON log lines to stderr. Nothing here logs request bodies or headers."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
    )
