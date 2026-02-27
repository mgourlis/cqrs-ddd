"""Request context for capturing HTTP request metadata.

Provides async-safe context variables for request-level information
useful for auditing, logging, and debugging.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class RequestContext:
    """HTTP request context for auditing and debugging.

    Captures request-level metadata that can be used for:
    - Audit event enrichment (IP address, user agent)
    - Request tracing (request_id)
    - Debugging and logging

    Attributes:
        request_id: Unique identifier for the request (correlation ID).
        ip_address: Client IP address (X-Forwarded-For or remote addr).
        user_agent: Client user agent string.
        origin: Request origin header (for CORS).
        path: Request path.
        method: HTTP method (GET, POST, etc.).
        headers: Request headers (may be filtered for security).
        query_string: Raw query string.
        created_at: When the request context was created.
    """

    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    origin: str | None = None
    path: str | None = None
    method: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    query_string: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, str | None]:
        """Convert to dictionary for logging/serialization.

        Returns:
            Dictionary representation.
        """
        return {
            "request_id": self.request_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "origin": self.origin,
            "path": self.path,
            "method": self.method,
            "query_string": self.query_string,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Context variable for request-scoped context
_request_context: ContextVar[RequestContext | None] = ContextVar(
    "request_context", default=None
)


def get_request_context() -> RequestContext | None:
    """Get the current request context.

    Returns:
        The current RequestContext or None if not set.
    """
    return _request_context.get()


def set_request_context(context: RequestContext) -> Token[RequestContext | None]:
    """Set request context in current async context.

    Args:
        context: The RequestContext to set.

    Returns:
        A Token that can be used to reset the context variable.

    Example:
        ```python
        token = set_request_context(RequestContext(
            request_id="abc-123",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0...",
            path="/api/users",
            method="GET",
        ))
        try:
            # Process request
            pass
        finally:
            reset_request_context(token)
        ```
    """
    return _request_context.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    """Reset request context to previous state.

    Args:
        token: The Token returned by set_request_context().
    """
    _request_context.reset(token)


def clear_request_context() -> None:
    """Clear request context.

    Sets the context to None. Use this for cleanup.
    """
    _request_context.set(None)


def get_request_id() -> str | None:
    """Get the current request ID.

    Returns:
        The current request ID or None.
    """
    ctx = get_request_context()
    return ctx.request_id if ctx else None


def get_client_ip() -> str | None:
    """Get the client IP address.

    Returns:
        The client IP or None.
    """
    ctx = get_request_context()
    return ctx.ip_address if ctx else None


def get_user_agent() -> str | None:
    """Get the client user agent.

    Returns:
        The user agent string or None.
    """
    ctx = get_request_context()
    return ctx.user_agent if ctx else None


__all__: list[str] = [
    "RequestContext",
    "get_request_context",
    "set_request_context",
    "reset_request_context",
    "clear_request_context",
    "get_request_id",
    "get_client_ip",
    "get_user_agent",
]
