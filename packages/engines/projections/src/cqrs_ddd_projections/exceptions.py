"""Projections package exceptions."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import HandlerError, PersistenceError


class ProjectionError(HandlerError):
    """Base for projection-related errors."""


class CheckpointError(PersistenceError):
    """Raised when checkpoint read/write fails."""


class ProjectionHandlerError(ProjectionError):
    """Raised when a projection handler fails (e.g. after retries)."""
