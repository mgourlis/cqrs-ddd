"""Primitives: exceptions, ID generation."""

from __future__ import annotations

from .exceptions import (
    ConcurrencyError,
    CQRSDDDError,
    DomainConcurrencyError,
    DomainError,
    EntityNotFoundError,
    EventStoreError,
    HandlerError,
    HandlerRegistrationError,
    InvariantViolationError,
    LockAcquisitionError,
    LockRollbackError,
    NotFoundError,
    OptimisticConcurrencyError,
    OptimisticLockingError,
    OutboxError,
    PublisherNotFoundError,
    ValidationError,
)
from .id_generator import IIDGenerator, UUID4Generator
from .locking import ResourceIdentifier

__all__ = [
    "ConcurrencyError",
    "CQRSDDDError",
    "DomainConcurrencyError",
    "DomainError",
    "OptimisticConcurrencyError",
    "EntityNotFoundError",
    "EventStoreError",
    "HandlerError",
    "HandlerRegistrationError",
    "IIDGenerator",
    "InvariantViolationError",
    "LockAcquisitionError",
    "LockRollbackError",
    "NotFoundError",
    "OptimisticLockingError",
    "OutboxError",
    "PublisherNotFoundError",
    "ResourceIdentifier",
    "UUID4Generator",
    "ValidationError",
]
