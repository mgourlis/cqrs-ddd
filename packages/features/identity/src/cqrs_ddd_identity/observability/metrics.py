"""Auth metrics helpers for Prometheus integration.

Provides authentication-specific metrics that can be used with the
existing cqrs_ddd_observability infrastructure or standalone.

Usage:
    ```python
    from cqrs_ddd_identity.observability import AuthMetrics, record_login

    # Use context manager for timing
    with AuthMetrics.operation("resolve", provider="keycloak"):
        principal = await provider.resolve(token)

    # Record events directly
    AuthMetrics.record_login_success("user-123", "keycloak")
    ```
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Generator

    from ..audit.events import AuthAuditEvent


@dataclass(frozen=True)
class AuthMetricLabels:
    """Standard labels for auth metrics."""

    provider: str = "unknown"
    method: str = "unknown"
    result: str = "success"


class _AuthMetricsRegistry:
    """Registry for auth Prometheus metrics.

    Lazily initializes Prometheus metrics on first use.
    """

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
                "Auth operation duration",
                ["provider", "method", "operation"],
            )
            self._counter = Counter(
                "auth_operations_total",
                "Auth operation count",
                ["provider", "method", "operation", "result"],
            )
            self._session_gauge = Gauge(
                "auth_active_sessions",
                "Number of active sessions",
                ["provider"],
            )
        except ImportError:
            _logger.debug("prometheus_client not available, metrics disabled")

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


# Global registry instance
_registry = _AuthMetricsRegistry()


class AuthMetrics:
    """Auth metrics helpers for recording authentication operations.

    This class provides context managers and helper methods for
    recording authentication metrics. It integrates with Prometheus
    when available but works as a no-op otherwise.
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

        Args:
            operation: Operation name (resolve, refresh, logout).
            provider: Identity provider name.
            method: Auth method (jwt, apikey, session).

        Yields:
            Nothing.
        """
        result = "success"
        start = time.monotonic()

        try:
            yield
        except Exception:
            result = "error"
            raise
        finally:
            duration = time.monotonic() - start

            if _registry.histogram:
                try:
                    _registry.histogram.labels(
                        provider=provider,
                        method=method,
                        operation=operation,
                    ).observe(duration)
                except Exception:
                    _logger.debug("Failed to record histogram")

            if _registry.counter:
                try:
                    _registry.counter.labels(
                        provider=provider,
                        method=method,
                        operation=operation,
                        result=result,
                    ).inc()
                except Exception:
                    _logger.debug("Failed to record counter")

    @staticmethod
    def record_event(event: AuthAuditEvent) -> None:
        """Record an audit event as a metric.

        Args:
            event: The audit event to record.
        """
        if not _registry.counter:
            return

        try:
            _registry.counter.labels(
                provider=event.provider,
                method=event.metadata.get("method", "unknown"),
                operation=event.event_type.value,
                result="success" if event.success else "failure",
            ).inc()
        except Exception:
            _logger.debug("Failed to record audit event metric")

    @staticmethod
    def increment_sessions(provider: str = "default") -> None:
        """Increment active sessions gauge.

        Args:
            provider: Provider name.
        """
        if _registry.session_gauge:
            try:
                _registry.session_gauge.labels(provider=provider).inc()
            except Exception:
                _logger.debug("Failed to increment session gauge")

    @staticmethod
    def decrement_sessions(provider: str = "default") -> None:
        """Decrement active sessions gauge.

        Args:
            provider: Provider name.
        """
        if _registry.session_gauge:
            try:
                _registry.session_gauge.labels(provider=provider).dec()
            except Exception:
                _logger.debug("Failed to decrement session gauge")


# Convenience functions
def record_login_success(user_id: str, provider: str, method: str = "jwt") -> None:
    """Record a successful login."""
    if _registry.counter:
        _registry.counter.labels(
            provider=provider,
            method=method,
            operation="login",
            result="success",
        ).inc()


def record_login_failure(provider: str, error_code: str = "unknown") -> None:
    """Record a failed login."""
    if _registry.counter:
        _registry.counter.labels(
            provider=provider,
            method=error_code,
            operation="login",
            result="failure",
        ).inc()


def record_logout(provider: str) -> None:
    """Record a logout."""
    if _registry.counter:
        _registry.counter.labels(
            provider=provider,
            method="unknown",
            operation="logout",
            result="success",
        ).inc()


__all__: list[str] = [
    "AuthMetricLabels",
    "AuthMetrics",
    "record_login_success",
    "record_login_failure",
    "record_logout",
]
