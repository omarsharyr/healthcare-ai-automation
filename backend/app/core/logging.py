"""Structured logs with a small allowlist of operational fields."""
import json
import logging
from datetime import datetime, timezone
from logging.config import dictConfig
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in ("method", "route", "status_code", "duration_ms", "attempt", "max_attempts"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        # Deliberately omit exc_info, stack_info, and arbitrary extra fields.
        return json.dumps(payload, ensure_ascii=True)


def logging_config(level: str = "INFO") -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": "app.core.logging.JsonFormatter"}},
        "handlers": {
            "console": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "json"},
            "null": {"class": "logging.NullHandler"},
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "uvicorn": {"handlers": ["console"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["null"], "propagate": False},
            "sqlalchemy": {"handlers": ["null"], "propagate": False},
            "psycopg": {"handlers": ["null"], "propagate": False},
            "httpx": {"handlers": ["null"], "propagate": False},
            "httpcore": {"handlers": ["null"], "propagate": False},
        },
    }


def configure_logging(level: str = "INFO") -> None:
    dictConfig(logging_config(level))
