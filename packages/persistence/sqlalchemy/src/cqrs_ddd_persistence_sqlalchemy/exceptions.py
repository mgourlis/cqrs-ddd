"""Exceptions for the SQLAlchemy persistence layer."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import (
    OptimisticConcurrencyError,
    PersistenceError,
)


class SQLAlchemyPersistenceError(PersistenceError):
    """Base exception for all SQLAlchemy-specific persistence errors."""


class SessionManagementError(SQLAlchemyPersistenceError):
    """Raised when session creation or management fails."""


class UnitOfWorkError(SQLAlchemyPersistenceError):
    """Raised when Unit of Work operations fail."""


class RepositoryError(SQLAlchemyPersistenceError):
    """Raised when repository operations fail."""


class TransactionError(SQLAlchemyPersistenceError):
    """Raised when transaction operations fail."""


class MappingError(SQLAlchemyPersistenceError):
    """Raised when mapping between domain entities and DB models fails."""


__all__: list[str] = [
    "OptimisticConcurrencyError",
    "MappingError",
    "RepositoryError",
    "SessionManagementError",
    "SQLAlchemyPersistenceError",
    "TransactionError",
    "UnitOfWorkError",
]
