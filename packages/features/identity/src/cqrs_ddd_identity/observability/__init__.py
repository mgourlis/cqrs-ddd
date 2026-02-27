"""Auth observability helpers for metrics and tracing.

This module provides optional metrics and tracing utilities for auth
operations. These are simple helper classes that integrate with
Prometheus and OpenTelemetry when available.

Usage:
    ```python
    from cqrs_ddd_identity.observability import AuthMetrics, AuthTracing

    # Record metrics
    with AuthMetrics.operation("resolve", provider="keycloak"):
        principal = await provider.resolve(token)

    # Create spans
    with AuthTracing.resolve_span("jwt", provider="keycloak") as span:
        principal = await provider.resolve(token)
        if span:
            AuthTracing.set_principal(span, principal)
    ```
"""

from __future__ import annotations

from .metrics import (
    AuthMetricLabels,
    AuthMetrics,
    record_login_failure,
    record_login_success,
    record_logout,
)
from .tracing import HAS_OTEL, AuthTracing

__all__: list[str] = [
    # Metrics
    "AuthMetricLabels",
    "AuthMetrics",
    "record_login_success",
    "record_login_failure",
    "record_logout",
    # Tracing
    "AuthTracing",
    "HAS_OTEL",
]
