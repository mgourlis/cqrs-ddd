"""Domain and infrastructure exceptions for cqrs-ddd-core."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .locking import ResourceIdentifier


class CQRSDDDError(Exception):
    """Root exception for the entire cqrs-ddd toolkit."""


class DomainError(CQRSDDDError):
    """Base class for all domain-related errors."""


class ConcurrencyError(CQRSDDDError):
    """Base class for all concurrency-related conflicts (both semantic and technical).

    Handlers catch this to trigger automated conflict resolution loops."""


class DomainConcurrencyError(ConcurrencyError, DomainError):
    """Raised when domain logic detects a semantic conflict.

    Usage: Raise this in your Aggregate Roots or Domain Services when business rules
    indicate that the user's intent is based on stale data.
    """


class NotFoundError(DomainError):
    """Raised when an aggregate or resource is not found."""


class EntityNotFoundError(NotFoundError):
    """Raised when a specific entity cannot be found by ID."""

    def __init__(self, entity_type: str, entity_id: object) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with id={entity_id!r} not found")


class InvariantViolationError(DomainError):
    """Raised when a domain invariant is violated."""


class ValidationError(CQRSDDDError):
    """Raised when command validation fails.

    Carries structured errors: ``{field: [messages]}``.
    """

    def __init__(self, errors: dict[str, list[str]] | str | None = None) -> None:
        if isinstance(errors, str):
            self.errors: dict[str, list[str]] = {"__root__": [errors]}
        elif errors is None:
            self.errors = {}
        else:
            self.errors = errors
        super().__init__(str(self.errors))


class EventStoreError(CQRSDDDError):
    """Raised when event-store operations fail."""


class OutboxError(CQRSDDDError):
    """Raised when outbox operations fail."""


class InfrastructureError(CQRSDDDError):
    """Base class for all infrastructure-related errors."""


class PersistenceError(InfrastructureError):
    """Base class for all persistence-related errors."""


class OptimisticLockingError(ConcurrencyError, PersistenceError):
    """Raised when the persistence layer detects a technical version mismatch.

    Usage: Built-in or custom repositories should raise this when an optimistic
    locking check (e.g., version column) fails during save.
    """


class HandlerError(CQRSDDDError):
    """Base class for all handler related errors (registration, lookup, execution)."""


class HandlerRegistrationError(HandlerError):
    """Raised when a handler registration conflict is detected.

    Usage: HandlerRegistry raises this when trying to register multiple
    handlers for a command or query type.
    """


class PublisherNotFoundError(HandlerError):
    """Raised when a publisher cannot be resolved for a specific topic/event.

    Usage: TopicRoutingPublisher raises this when no specific route
    exists and no default publisher is configured.
    """


# ── Locking Exceptions ───────────────────────────────────────────────


class LockAcquisitionError(ConcurrencyError):
    """Failed to acquire lock with detailed context.

    Provides diagnostic information about which resource failed
    and under what conditions.
    """

    def __init__(
        self,
        resource: ResourceIdentifier,
        timeout: float,
        reason: str | None = None,
    ) -> None:
        self.resource = resource
        self.timeout = timeout
        self.reason = reason

        msg = (
            f"Failed to acquire {resource.lock_mode} lock on "
            f"{resource.resource_type}:{resource.resource_id} "
            f"within {timeout}s"
        )
        if reason:
            msg += f" - {reason}"

        super().__init__(msg)


class LockRollbackError(ConcurrencyError):
    """Failed to rollback locks after partial acquisition failure.

    Contains information about how many locks were successfully
    released and which ones failed.
    """

    def __init__(
        self,
        attempted: int,
        failed: int,
        errors: list[Exception],
    ) -> None:
        self.attempted = attempted
        self.failed = failed
        self.errors = errors

        super().__init__(
            f"Lock rollback incomplete: {failed}/{attempted} releases failed. "
            f"First error: {errors[0] if errors else 'unknown'}"
        )
