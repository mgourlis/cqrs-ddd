"""Tenant tracing helpers for OpenTelemetry integration.

Provides multitenancy-specific tracing that integrates with the
existing cqrs_ddd_observability infrastructure or standalone.

Usage:
    ```python
    from cqrs_ddd_multitenancy.observability import TenantTracing

    with TenantTracing.resolve_span("header") as span:
        tenant_id = await resolver.resolve(request)
        if span:
            TenantTracing.set_tenant(span, tenant_id)
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
            self._tracer = trace.get_tracer("cqrs-ddd-multitenancy")
        self._initialized = True

    @property
    def tracer(self) -> Any:
        self._ensure_initialized()
        return self._tracer


_tracer_registry = _TracerRegistry()


class TenantTracing:
    """Tenant tracing helper for OpenTelemetry.

    Provides span creation and attribute setting helpers for
    tenant operations. Integrates with OpenTelemetry when available.
    """

    @staticmethod
    @contextmanager
    def resolve_span(
        resolver: str,
        **attributes: Any,
    ) -> Generator[Any, None, None]:
        """Context manager for tenant resolution spans.

        Args:
            resolver: The resolver name (e.g., "header", "jwt").
            **attributes: Additional span attributes.

        Yields:
            The span object (or None if OTel not available).
        """
        if not HAS_OTEL or not _tracer_registry.tracer:
            yield None
            return

        with _tracer_registry.tracer.start_as_current_span(
            f"tenant.resolve.{resolver}"
        ) as span:
            span.set_attribute("tenant.resolver", resolver)
            span.set_attribute("tenant.operation", "resolve")

            for key, value in attributes.items():
                span.set_attribute(f"tenant.{key}", str(value))

            try:
                yield span
                span.set_status(Status(StatusCode.OK))
                span.set_attribute("tenant.outcome", "success")
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR))
                span.set_attribute("tenant.outcome", "error")
                span.record_exception(exc)
                raise

    @staticmethod
    @contextmanager
    def schema_switch_span(
        tenant_id: str,
        **attributes: Any,
    ) -> Generator[Any, None, None]:
        """Context manager for schema switch spans.

        Args:
            tenant_id: The tenant ID.
            **attributes: Additional span attributes.

        Yields:
            The span object (or None if OTel not available).
        """
        if not HAS_OTEL or not _tracer_registry.tracer:
            yield None
            return

        with _tracer_registry.tracer.start_as_current_span(
            "tenant.schema.switch"
        ) as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("tenant.operation", "switch_schema")

            for key, value in attributes.items():
                span.set_attribute(f"tenant.{key}", str(value))

            try:
                yield span
                span.set_status(Status(StatusCode.OK))
                span.set_attribute("tenant.outcome", "success")
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR))
                span.set_attribute("tenant.outcome", "error")
                span.record_exception(exc)
                raise

    @staticmethod
    @contextmanager
    def database_switch_span(
        tenant_id: str,
        **attributes: Any,
    ) -> Generator[Any, None, None]:
        """Context manager for database switch spans.

        Args:
            tenant_id: The tenant ID.
            **attributes: Additional span attributes.

        Yields:
            The span object (or None if OTel not available).
        """
        if not HAS_OTEL or not _tracer_registry.tracer:
            yield None
            return

        with _tracer_registry.tracer.start_as_current_span(
            "tenant.database.switch"
        ) as span:
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("tenant.operation", "switch_database")

            for key, value in attributes.items():
                span.set_attribute(f"tenant.{key}", str(value))

            try:
                yield span
                span.set_status(Status(StatusCode.OK))
                span.set_attribute("tenant.outcome", "success")
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR))
                span.set_attribute("tenant.outcome", "error")
                span.record_exception(exc)
                raise

    @staticmethod
    def set_tenant(span: Any, tenant_id: str) -> None:
        """Set tenant ID on a span.

        Args:
            span: The OpenTelemetry span.
            tenant_id: The tenant ID.
        """
        if span and HAS_OTEL:
            span.set_attribute("tenant.id", tenant_id)

    @staticmethod
    def set_isolation_strategy(span: Any, strategy: str) -> None:
        """Set isolation strategy on a span.

        Args:
            span: The OpenTelemetry span.
            strategy: The isolation strategy name.
        """
        if span and HAS_OTEL:
            span.set_attribute("tenant.isolation_strategy", strategy)

    @staticmethod
    def set_schema(span: Any, schema_name: str) -> None:
        """Set schema name on a span.

        Args:
            span: The OpenTelemetry span.
            schema_name: The schema name.
        """
        if span and HAS_OTEL:
            span.set_attribute("tenant.schema", schema_name)

    @staticmethod
    def set_database(span: Any, database_name: str) -> None:
        """Set database name on a span.

        Args:
            span: The OpenTelemetry span.
            database_name: The database name.
        """
        if span and HAS_OTEL:
            span.set_attribute("tenant.database", database_name)
