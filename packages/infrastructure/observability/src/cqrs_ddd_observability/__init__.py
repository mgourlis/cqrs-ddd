"""Observability — tracing, metrics, and structured logging."""

from __future__ import annotations

from . import auth as auth_observability
from .context import ObservabilityContext
from .exceptions import ObservabilityError
from .hooks import (
    DEFAULT_FRAMEWORK_TRACE_OPERATIONS,
    ObservabilityInstrumentationHook,
    install_framework_hooks,
)
from .metrics import MetricsMiddleware
from .payload_tracing import PayloadTracingMiddleware
from .sentry import SentryMiddleware
from .structured_logging import StructuredLoggingMiddleware
from .tracing import TracingMiddleware

__all__ = [
    "install_framework_hooks",
    "DEFAULT_FRAMEWORK_TRACE_OPERATIONS",
    "ObservabilityInstrumentationHook",
    "MetricsMiddleware",
    "PayloadTracingMiddleware",
    "ObservabilityContext",
    "ObservabilityError",
    "SentryMiddleware",
    "StructuredLoggingMiddleware",
    "TracingMiddleware",
    "auth_observability",
]
