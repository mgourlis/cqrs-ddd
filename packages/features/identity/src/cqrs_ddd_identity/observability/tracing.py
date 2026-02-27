"""Auth tracing helpers for OpenTelemetry integration.

Provides authentication-specific tracing that integrates with the
existing cqrs_ddd_observability infrastructure or standalone.

Usage:
    ```python
    from cqrs_ddd_identity.observability import AuthTracing

    with AuthTracing.resolve_span("jwt", provider="keycloak") as span:
        principal = await provider.resolve(token)
        if span:
            AuthTracing.set_principal(span, principal)
    ```
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

_logger = logging.getLogger(__name__)

# Try to import OpenTelemetry (optional dependency)
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False
    trace = None
    Status = None
    StatusCode = None


class _TracerRegistry:
    """Lazy tracer initialization."""

    def __init__(self) -> None:
        self._tracer = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        if HAS_OTEL and trace:
            self._tracer = trace.get_tracer("cqrs-ddd-identity")
        self._initialized = True

    @property
    def tracer(self) -> Any:
        self._ensure_initialized()
        return self._tracer


_registry = _TracerRegistry()


class AuthTracing:
    """Auth tracing helpers for OpenTelemetry.

    This class provides context managers and helper methods for
    creating spans around authentication operations. It integrates
    with OpenTelemetry when available but works as a no-op otherwise.
    """

    @staticmethod
    @contextmanager
    def span(
        operation: str,
        *,
        provider: str = "unknown",
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Any, None, None]:
        """Context manager for a traced auth operation.

        Args:
            operation: Operation name (resolve, refresh, logout).
            provider: Identity provider name.
            attributes: Additional span attributes.

        Yields:
            Span object or None if tracing disabled.
        """
        tracer = _registry.tracer
        if not tracer:
            yield None
            return

        span_name = f"auth.{operation}"
        with tracer.start_as_current_span(span_name) as span:
            try:
                span.set_attribute("auth.operation", operation)
                span.set_attribute("auth.provider", provider)

                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, str(value))

                yield span

            except Exception as e:
                if Status and StatusCode:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                raise

    @staticmethod
    @contextmanager
    def resolve_span(
        method: str,
        *,
        provider: str = "unknown",
    ) -> Generator[Any, None, None]:
        """Context manager for resolve operations.

        Args:
            method: Authentication method (jwt, apikey, session).
            provider: Identity provider name.

        Yields:
            Span object or None.
        """
        with AuthTracing.span(
            "resolve",
            provider=provider,
            attributes={"auth.method": method},
        ) as span:
            yield span

    @staticmethod
    @contextmanager
    def refresh_span(
        *,
        provider: str = "unknown",
    ) -> Generator[Any, None, None]:
        """Context manager for refresh operations.

        Args:
            provider: Identity provider name.

        Yields:
            Span object or None.
        """
        with AuthTracing.span("refresh", provider=provider) as span:
            yield span

    @staticmethod
    @contextmanager
    def logout_span(
        *,
        provider: str = "unknown",
    ) -> Generator[Any, None, None]:
        """Context manager for logout operations.

        Args:
            provider: Identity provider name.

        Yields:
            Span object or None.
        """
        with AuthTracing.span("logout", provider=provider) as span:
            yield span

    @staticmethod
    def set_principal(span: Any, principal: Any) -> None:
        """Set principal attributes on a span.

        Args:
            span: Span object.
            principal: The resolved Principal.
        """
        if not span:
            return

        span.set_attribute("auth.user_id", principal.user_id)
        span.set_attribute("auth.username", principal.username)

        if principal.tenant_id:
            span.set_attribute("auth.tenant_id", principal.tenant_id)

        if principal.auth_method:
            span.set_attribute("auth.method", principal.auth_method)

        if principal.roles:
            span.set_attribute("auth.roles", ",".join(principal.roles))

        if principal.expires_at:
            span.set_attribute("auth.expires_at", principal.expires_at.isoformat())

    @staticmethod
    def set_success(span: Any) -> None:
        """Mark span as successful."""
        if span and Status and StatusCode:
            span.set_status(Status(StatusCode.OK))

    @staticmethod
    def set_error(span: Any, error: Exception) -> None:
        """Mark span as failed with error."""
        if span and Status and StatusCode:
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.record_exception(error)


__all__: list[str] = [
    "AuthTracing",
    "HAS_OTEL",
]
