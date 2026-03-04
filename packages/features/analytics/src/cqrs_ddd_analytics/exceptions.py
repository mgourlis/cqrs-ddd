"""Analytics package exceptions."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import CQRSDDDError, InfrastructureError


class AnalyticsError(CQRSDDDError):
    """Base exception for all analytics-related errors."""


class SchemaError(AnalyticsError):
    """Raised when an analytics schema is invalid or mismatched."""


class SinkConnectionError(AnalyticsError, InfrastructureError):
    """Raised when the analytics sink cannot connect or write to storage."""


class BufferFlushError(AnalyticsError):
    """Raised when the buffer fails to flush rows to the sink."""
