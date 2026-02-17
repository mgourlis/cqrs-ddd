"""Domain events emitted during background job lifecycle transitions."""

from __future__ import annotations

from pydantic import ConfigDict

from cqrs_ddd_core.domain.events import DomainEvent


class JobCreated(DomainEvent):
    """Emitted when a new background job is registered."""

    model_config = ConfigDict(frozen=True)

    job_type: str
    total_items: int = 0


class JobStarted(DomainEvent):
    """Emitted when a background job begins processing."""

    model_config = ConfigDict(frozen=True)


class JobCompleted(DomainEvent):
    """Emitted when a background job finishes successfully."""

    model_config = ConfigDict(frozen=True)


class JobFailed(DomainEvent):
    """Emitted when a background job fails."""

    model_config = ConfigDict(frozen=True)

    error_message: str


class JobRetried(DomainEvent):
    """Emitted when a failed background job is retried."""

    model_config = ConfigDict(frozen=True)

    retry_count: int


class JobCancelled(DomainEvent):
    """Emitted when a background job is cancelled by user action."""

    model_config = ConfigDict(frozen=True)
