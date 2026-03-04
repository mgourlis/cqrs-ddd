"""Tenant metrics helpers for Prometheus integration.

Provides multitenancy-specific metrics that integrate with the
existing cqrs_ddd_observability infrastructure or standalone.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

_logger = logging.getLogger(__name__)

# Try to import Prometheus (optional dependency)
try:
    from prometheus_client import Counter, Histogram

    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    Counter = None
    Histogram = None


@dataclass(frozen=True)
class TenantMetricLabels:
    """Standard labels for tenant metrics."""

    operation: str
    resolver: str | None = None
    strategy: str | None = None
    outcome: str = "success"


class _MetricsRegistry:
    """Lazy metrics initialization."""

    def __init__(self) -> None:
        self._initialized = False
        self._resolution_duration: Any = None
        self._resolution_total: Any = None
        self._schema_switch_duration: Any = None
        self._schema_switch_total: Any = None

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        if HAS_PROMETHEUS:
            # Tenant resolution metrics
            self._resolution_duration = Histogram(
                "tenant_resolution_duration_seconds",
                "Time spent resolving tenant ID",
                ["resolver", "outcome"],
            )

            self._resolution_total = Counter(
                "tenant_resolution_total",
                "Total tenant resolution operations",
                ["resolver", "outcome"],
            )

            # Schema switching metrics
            self._schema_switch_duration = Histogram(
                "tenant_schema_switch_duration_seconds",
                "Time spent switching PostgreSQL schema",
                ["outcome"],
            )

            self._schema_switch_total = Counter(
                "tenant_schema_switch_total",
                "Total schema switch operations",
                ["outcome"],
            )

        self._initialized = True

    @property
    def resolution_duration(self) -> Any:
        self._ensure_initialized()
        return self._resolution_duration

    @property
    def resolution_total(self) -> Any:
        self._ensure_initialized()
        return self._resolution_total

    @property
    def schema_switch_duration(self) -> Any:
        self._ensure_initialized()
        return self._schema_switch_duration

    @property
    def schema_switch_total(self) -> Any:
        self._ensure_initialized()
        return self._schema_switch_total


_registry = _MetricsRegistry()


class TenantMetrics:
    """Tenant metrics recording helper.

    Provides context managers for recording operation durations
    and counters. Integrates with Prometheus when available.
    """

    @staticmethod
    @contextmanager
    def operation(
        operation: str,
        *,
        resolver: str | None = None,
        strategy: str | None = None,
    ) -> Generator[None, None, None]:
        """Context manager for timing tenant operations.

        Args:
            operation: The operation name (e.g., "resolve", "switch_schema").
            resolver: The resolver name (optional).
            strategy: The isolation strategy (optional).

        Yields:
            None
        """
        if not HAS_PROMETHEUS:
            yield
            return

        import time

        start_time = time.perf_counter()
        outcome = "success"

        try:
            yield
        except Exception:
            outcome = "error"
            raise
        finally:
            duration = time.perf_counter() - start_time

            # Record based on operation type
            if operation == "resolve" and resolver:
                _registry.resolution_duration.labels(
                    resolver=resolver,
                    outcome=outcome,
                ).observe(duration)

                _registry.resolution_total.labels(
                    resolver=resolver,
                    outcome=outcome,
                ).inc()
            elif operation == "switch_schema":
                _registry.schema_switch_duration.labels(
                    outcome=outcome,
                ).observe(duration)

                _registry.schema_switch_total.labels(
                    outcome=outcome,
                ).inc()

    @staticmethod
    def record_resolution(
        resolver: str,
        duration: float,
        outcome: str = "success",
    ) -> None:
        """Record a tenant resolution operation.

        Args:
            resolver: The resolver name.
            duration: The operation duration in seconds.
            outcome: The outcome ("success" or "error").
        """
        if not HAS_PROMETHEUS:
            return

        _registry.resolution_duration.labels(
            resolver=resolver,
            outcome=outcome,
        ).observe(duration)

        _registry.resolution_total.labels(
            resolver=resolver,
            outcome=outcome,
        ).inc()


def record_resolution_success(resolver: str, duration: float) -> None:
    """Record a successful tenant resolution.

    Args:
        resolver: The resolver name.
        duration: The operation duration in seconds.
    """
    TenantMetrics.record_resolution(resolver, duration, "success")


def record_resolution_failure(resolver: str, duration: float) -> None:
    """Record a failed tenant resolution.

    Args:
        resolver: The resolver name.
        duration: The operation duration in seconds.
    """
    TenantMetrics.record_resolution(resolver, duration, "error")


def record_schema_switch(duration: float, outcome: str = "success") -> None:
    """Record a schema switch operation.

    Args:
        duration: The operation duration in seconds.
        outcome: The outcome ("success" or "error").
    """
    if not HAS_PROMETHEUS:
        return

    _registry.schema_switch_duration.labels(
        outcome=outcome,
    ).observe(duration)

    _registry.schema_switch_total.labels(
        outcome=outcome,
    ).inc()
