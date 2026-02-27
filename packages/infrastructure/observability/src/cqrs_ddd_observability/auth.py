"""Auth observability — metrics and tracing for authentication operations.

This module provides authentication-specific observability utilities that
integrate with the existing cqrs_ddd_observability infrastructure.

Prometheus Metrics:
    - auth_operation_duration_seconds{provider, method, operation}
    - auth_operations_total{provider, method, operation, result}
    - auth_active_sessions{provider}

OpenTelemetry Tracing:
    - auth.resolve.{method}
    - auth.refresh
    - auth.logout
    - auth.mfa.verify

Usage:
    ```python
    from cqrs_ddd_observability.auth import (
        AuthMetrics,
        AuthTracing,
        record_login_success,
        record_login_failure,
    )

    # In your authentication middleware
    with AuthMetrics.operation("resolve", provider="keycloak", method="jwt"):
        with AuthTracing.resolve_span(method="jwt", provider="keycloak") as span:
            principal = await provider.resolve(token)
            if span:
                AuthTracing.set_principal(span, principal)
    ```
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthLabels:
    """Standard labels for auth observability.

    Attributes:
        provider: Identity provider name (keycloak, database, apikey).
        method: Authentication method (jwt, session, apikey, mfa).
        operation: Operation type (resolve, refresh, logout, verify).
        result: Operation result (success, failure).
    """

    provider: str = "unknown"
    method: str = "unknown"
    operation: str = "unknown"
    result: str = "success"


# ═══════════════════════════════════════════════════════════════════════════
# METRICS
# ═══════════════════════════════════════════════════════════════════════════


class _AuthMetricsRegistry:
    """Lazy registry for auth Prometheus metrics."""

    def __init__(self) -> None:
        self._histogram: Any = None
        self._counter: Any = None
        self._session_gauge: Any = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initialize Prometheus metrics if available."""
        if self._initialized:
            return

        try:
            from prometheus_client import Counter, Gauge, Histogram

            self._histogram = Histogram(
                "auth_operation_duration_seconds",
                "Duration of authentication operations",
                ["provider", "method", "operation"],
                buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
            )
            self._counter = Counter(
                "auth_operations_total",
                "Total count of authentication operations",
                ["provider", "method", "operation", "result"],
            )
            self._session_gauge = Gauge(
                "auth_active_sessions",
                "Number of active authentication sessions",
                ["provider"],
            )
            _logger.debug("Auth Prometheus metrics initialized")
        except ImportError:
            _logger.debug("prometheus_client not available, auth metrics disabled")

        self._initialized = True

    @property
    def histogram(self) -> Any:
        self._ensure_initialized()
        return self._histogram

    @property
    def counter(self) -> Any:
        self._ensure_initialized()
        return self._counter

    @property
    def session_gauge(self) -> Any:
        self._ensure_initialized()
        return self._session_gauge


_metrics = _AuthMetricsRegistry()


class AuthMetrics:
    """Prometheus metrics helpers for authentication operations.

    This class provides context managers and helper methods for
    recording authentication metrics. It integrates with Prometheus
    when available but gracefully degrades to no-op.
    """

    @staticmethod
    @contextmanager
    def operation(
        operation: str,
        *,
        provider: str = "unknown",
        method: str = "unknown",
    ) -> Generator[None, None, None]:
        """Context manager for timing an auth operation.

        Automatically records duration histogram and outcome counter.

        Args:
            operation: Operation name (resolve, refresh, logout, verify).
            provider: Identity provider name.
            method: Auth method (jwt, apikey, session, mfa).

        Yields:
            Nothing.

        Example:
            ```python
            with AuthMetrics.operation("resolve", provider="keycloak", method="jwt"):
                principal = await provider.resolve(token)
            ```
        """
        result = "success"
        start = time.monotonic()

        try:
            yield
        except Exception:
            result = "failure"
            raise
        finally:
            duration = time.monotonic() - start

            if _metrics.histogram:
                try:
                    _metrics.histogram.labels(
                        provider=provider,
                        method=method,
                        operation=operation,
                    ).observe(duration)
                except Exception:  # noqa: BLE001
                    _logger.debug("Failed to record auth histogram")

            if _metrics.counter:
                try:
                    _metrics.counter.labels(
                        provider=provider,
                        method=method,
                        operation=operation,
                        result=result,
                    ).inc()
                except Exception:  # noqa: BLE001
                    _logger.debug("Failed to record auth counter")

    @staticmethod
    def record(labels: AuthLabels) -> None:
        """Record a single auth event.

        Args:
            labels: Auth labels describing the event.
        """
        if _metrics.counter:
            try:
                _metrics.counter.labels(
                    provider=labels.provider,
                    method=labels.method,
                    operation=labels.operation,
                    result=labels.result,
                ).inc()
            except Exception:  # noqa: BLE001
                _logger.debug("Failed to record auth event")

    @staticmethod
    def increment_sessions(provider: str = "default") -> None:
        """Increment active sessions gauge.

        Call when a new session is created.

        Args:
            provider: Provider name for labeling.
        """
        if _metrics.session_gauge:
            try:
                _metrics.session_gauge.labels(provider=provider).inc()
            except Exception:  # noqa: BLE001
                _logger.debug("Failed to increment session gauge")

    @staticmethod
    def decrement_sessions(provider: str = "default") -> None:
        """Decrement active sessions gauge.

        Call when a session is destroyed.

        Args:
            provider: Provider name for labeling.
        """
        if _metrics.session_gauge:
            try:
                _metrics.session_gauge.labels(provider=provider).dec()
            except Exception:  # noqa: BLE001
                _logger.debug("Failed to decrement session gauge")


# ═══════════════════════════════════════════════════════════════════════════
# TRACING
# ═══════════════════════════════════════════════════════════════════════════


class _AuthTracerRegistry:
    """Lazy registry for OpenTelemetry tracer."""

    def __init__(self) -> None:
        self._tracer = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        try:
            from opentelemetry import trace

            self._tracer = trace.get_tracer("cqrs-ddd-auth")
            _logger.debug("Auth OpenTelemetry tracer initialized")
        except ImportError:
            _logger.debug("opentelemetry-api not available, auth tracing disabled")
        self._initialized = True

    @property
    def tracer(self) -> Any:
        self._ensure_initialized()
        return self._tracer

    @property
    def available(self) -> bool:
        self._ensure_initialized()
        return self._tracer is not None


_tracer = _AuthTracerRegistry()


class AuthTracing:
    """OpenTelemetry tracing helpers for authentication operations.

    This class provides context managers for creating spans around
    authentication operations. It integrates with OpenTelemetry when
    available but gracefully degrades to no-op.
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
            operation: Operation name (resolve, refresh, logout, verify).
            provider: Identity provider name.
            attributes: Additional span attributes.

        Yields:
            Span object or None if tracing unavailable.

        Example:
            ```python
            with AuthTracing.span("resolve", provider="keycloak") as span:
                principal = await provider.resolve(token)
            ```
        """
        if not _tracer.available:
            yield None
            return

        span_name = f"auth.{operation}"
        with _tracer.tracer.start_as_current_span(span_name) as span:
            try:
                span.set_attribute("auth.operation", operation)
                span.set_attribute("auth.provider", provider)

                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, str(value))

                yield span

            except Exception as e:
                try:
                    from opentelemetry.trace import Status, StatusCode

                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                except ImportError:
                    pass
                raise

    @staticmethod
    @contextmanager
    def resolve_span(
        method: str,
        *,
        provider: str = "unknown",
    ) -> Generator[Any, None, None]:
        """Context manager for token resolution operations.

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
        """Context manager for token refresh operations.

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
    @contextmanager
    def mfa_span(
        method: str = "totp",
        *,
        provider: str = "unknown",
    ) -> Generator[Any, None, None]:
        """Context manager for MFA verification operations.

        Args:
            method: MFA method (totp, sms, backup_code).
            provider: Identity provider name.

        Yields:
            Span object or None.
        """
        with AuthTracing.span(
            "mfa.verify",
            provider=provider,
            attributes={"auth.mfa.method": method},
        ) as span:
            yield span

    @staticmethod
    def set_principal(span: Any, principal: Any) -> None:
        """Set principal attributes on a span.

        Args:
            span: Span object (from context manager).
            principal: Principal value object with user_id, username, etc.
        """
        if not span:
            return

        span.set_attribute("auth.user_id", str(getattr(principal, "user_id", "")))
        span.set_attribute("auth.username", str(getattr(principal, "username", "")))

        if hasattr(principal, "tenant_id") and principal.tenant_id:
            span.set_attribute("auth.tenant_id", str(principal.tenant_id))

        if hasattr(principal, "auth_method") and principal.auth_method:
            span.set_attribute("auth.method", str(principal.auth_method))

        if hasattr(principal, "roles") and principal.roles:
            span.set_attribute("auth.roles", ",".join(str(r) for r in principal.roles))

        if hasattr(principal, "expires_at") and principal.expires_at:
            span.set_attribute("auth.expires_at", principal.expires_at.isoformat())

    @staticmethod
    def set_success(span: Any) -> None:
        """Mark span as successful."""
        if not span:
            return
        try:
            from opentelemetry.trace import Status, StatusCode

            span.set_status(Status(StatusCode.OK))
        except ImportError:
            pass

    @staticmethod
    def set_error(span: Any, error: Exception) -> None:
        """Mark span as failed with error.

        Args:
            span: Span object.
            error: The exception that occurred.
        """
        if not span:
            return
        try:
            from opentelemetry.trace import Status, StatusCode

            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.record_exception(error)
        except ImportError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


def record_login_success(
    *,
    user_id: str = "",  # noqa: ARG001
    provider: str,
    method: str = "jwt",
) -> None:
    """Record a successful login event.

    Args:
        user_id: The authenticated user's ID.
        provider: Identity provider name.
        method: Authentication method used.
    """
    AuthMetrics.record(
        AuthLabels(
            provider=provider,
            method=method,
            operation="login",
            result="success",
        )
    )


def record_login_failure(
    *,
    provider: str,
    error_code: str = "unknown",  # noqa: ARG001
    method: str = "unknown",
) -> None:
    """Record a failed login event.

    Args:
        provider: Identity provider name.
        error_code: Error code or type.
        method: Authentication method attempted.
    """
    AuthMetrics.record(
        AuthLabels(
            provider=provider,
            method=method,
            operation="login",
            result="failure",
        )
    )


def record_logout(provider: str, method: str = "unknown") -> None:
    """Record a logout event.

    Args:
        provider: Identity provider name.
        method: Authentication method that was used.
    """
    AuthMetrics.record(
        AuthLabels(
            provider=provider,
            method=method,
            operation="logout",
            result="success",
        )
    )


def record_token_refresh(provider: str, method: str = "jwt") -> None:
    """Record a token refresh event.

    Args:
        provider: Identity provider name.
        method: Token type being refreshed.
    """
    AuthMetrics.record(
        AuthLabels(
            provider=provider,
            method=method,
            operation="refresh",
            result="success",
        )
    )


def record_mfa_verification(
    provider: str,
    method: str = "totp",
    success: bool = True,
) -> None:
    """Record an MFA verification event.

    Args:
        provider: Identity provider name.
        method: MFA method used (totp, sms, backup_code).
        success: Whether verification succeeded.
    """
    AuthMetrics.record(
        AuthLabels(
            provider=provider,
            method=method,
            operation="mfa.verify",
            result="success" if success else "failure",
        )
    )


__all__: list[str] = [
    # Data classes
    "AuthLabels",
    # Metrics
    "AuthMetrics",
    # Tracing
    "AuthTracing",
    # Convenience functions
    "record_login_success",
    "record_login_failure",
    "record_logout",
    "record_token_refresh",
    "record_mfa_verification",
]
