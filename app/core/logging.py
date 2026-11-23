"""Structured JSON logging configuration using structlog."""

import logging
import sys
import structlog

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configures structlog once for machine-readable JSON logs."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str):
    """Returns a bound structlog JSON logger for the given module."""
    configure_logging()
    return structlog.get_logger(module=name)
