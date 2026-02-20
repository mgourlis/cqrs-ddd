"""Correlation ID management — fundamental to distributed tracing."""

from __future__ import annotations

import contextlib
import functools
import uuid
from contextvars import ContextVar, copy_context
from typing import Any

# ContextVar for correlation/causation tracking across async boundaries.
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_causation_id: ContextVar[str | None] = ContextVar("causation_id", default=None)


def get_correlation_id() -> str | None:
    """Get current correlation ID from context."""
    return _correlation_id.get()


def set_correlation_id(correlation_id: str | None) -> None:
    """Set correlation ID in context."""
    _correlation_id.set(correlation_id)


def get_causation_id() -> str | None:
    """Get current causation ID from context."""
    return _causation_id.get()


def set_causation_id(causation_id: str | None) -> None:
    """Set causation ID in context."""
    _causation_id.set(causation_id)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return str(uuid.uuid4())


def get_context_vars() -> dict[str, str | None]:
    """Get all correlation context variables for background task spawning."""
    return {
        "correlation_id": get_correlation_id(),
        "causation_id": get_causation_id(),
    }


def set_context_vars(**kwargs: str | None) -> None:
    """Set correlation context variables (useful for background tasks)."""
    if "correlation_id" in kwargs:
        set_correlation_id(kwargs["correlation_id"])
    if "causation_id" in kwargs:
        set_causation_id(kwargs["causation_id"])


class CorrelationIdPropagator:
    """Middleware that ensures correlation_id and causation_id flow end-to-end."""

    def __init__(self, correlation_id_key: str = "correlation_id") -> None:
        self._key = correlation_id_key

    async def __call__(self, message: Any, next_handler: Any) -> Any:
        existing_correlation = get_correlation_id()

        # Inject correlation ID into message.
        if existing_correlation and hasattr(message, "model_copy"):
            message = message.model_copy(update={self._key: existing_correlation})
        elif existing_correlation and hasattr(message, "__setattr__"):
            with contextlib.suppress(AttributeError, TypeError):
                object.__setattr__(message, self._key, existing_correlation)

        # Extract from message if present.
        if hasattr(message, self._key):
            cid = getattr(message, self._key, None)
            if cid:
                set_correlation_id(str(cid))

        # Set causation ID if message is an event (event -> command chain).
        if hasattr(message, "event_id"):
            event_id = getattr(message, "event_id", None)
            if event_id:
                set_causation_id(str(event_id))

        return await next_handler(message)


def with_correlation_context(func: Any) -> Any:
    """Decorator to run function with current correlation context."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        ctx = copy_context()
        return await ctx.run(func, *args, **kwargs)

    return wrapper
