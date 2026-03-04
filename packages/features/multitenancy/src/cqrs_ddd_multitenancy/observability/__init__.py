"""Multitenancy observability helpers for metrics and tracing.

This module provides optional metrics and tracing utilities for tenant
operations. These integrate with Prometheus and OpenTelemetry when available.

Usage:
    ```python
    from cqrs_ddd_multitenancy.observability import TenantMetrics, TenantTracing

    # Record metrics
    with TenantMetrics.operation("resolve", resolver="header"):
        tenant_id = await resolver.resolve(request)

    # Create spans
    with TenantTracing.resolve_span("header") as span:
        tenant_id = await resolver.resolve(request)
        if span:
            TenantTracing.set_tenant(span, tenant_id)
    ```
"""

from __future__ import annotations

from .metrics import (
    TenantMetricLabels,
    TenantMetrics,
    record_resolution_failure,
    record_resolution_success,
    record_schema_switch,
)
from .tracing import HAS_OTEL, TenantTracing

__all__: list[str] = [
    # Metrics
    "TenantMetricLabels",
    "TenantMetrics",
    "record_resolution_success",
    "record_resolution_failure",
    "record_schema_switch",
    # Tracing
    "TenantTracing",
    "HAS_OTEL",
]
