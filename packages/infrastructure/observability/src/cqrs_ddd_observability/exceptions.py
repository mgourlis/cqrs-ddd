"""Observability exceptions — non-critical, never block commands."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import InfrastructureError


class ObservabilityError(InfrastructureError):
    """Raised by observability code;
    callers should catch and log, never fail the request."""
