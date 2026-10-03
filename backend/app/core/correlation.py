"""Opaque UUID correlation only; never derive identifiers from healthcare data."""
from contextvars import ContextVar
from uuid import UUID, uuid4

correlation_id: ContextVar[UUID | None] = ContextVar("correlation_id", default=None)


def select_correlation_id(value: str | None) -> UUID:
    try:
        parsed = UUID(value) if value and len(value) == 36 else None
        if parsed is not None and parsed.version == 4:
            return parsed
    except ValueError:
        pass
    return uuid4()


def current_correlation_id() -> UUID | None:
    return correlation_id.get()
