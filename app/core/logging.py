from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.config import LogFormat, Settings


def configure_logging(settings: Settings) -> None:
    """Configure standard logging and structlog for the current process."""
    level = getattr(logging, settings.log_level)
    renderer: structlog.types.Processor
    if settings.effective_log_format is LogFormat.JSON:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
        force=True,
    )
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.EventRenamer("event"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a structured logger optionally bound to stable context."""
    return structlog.get_logger().bind(**initial_values)

