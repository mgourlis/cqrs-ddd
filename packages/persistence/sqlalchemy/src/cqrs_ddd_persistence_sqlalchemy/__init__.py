"""SQLAlchemy Persistence Adapter."""

from __future__ import annotations

from .core.event_store import SQLAlchemyEventStore
from .core.model_mapper import ModelMapper
from .core.models import (
    Base,
    OutboxMessage,
    OutboxStatus,
    StoredEventModel,
)
from .core.outbox import SQLAlchemyOutboxStorage
from .core.repository import SQLAlchemyRepository
from .core.uow import SQLAlchemyUnitOfWork
from .exceptions import (
    MappingError,
    OptimisticConcurrencyError,
    RepositoryError,
    SessionManagementError,
    SQLAlchemyPersistenceError,
    TransactionError,
    UnitOfWorkError,
)
from .specifications import (
    SQLAlchemyHookResult,
    SQLAlchemyOperator,
    SQLAlchemyOperatorRegistry,
    SQLAlchemyResolutionContext,
    apply_query_options,
    build_sqla_filter,
)

__all__ = [
    # Core
    "ModelMapper",
    "SQLAlchemyRepository",
    "SQLAlchemyUnitOfWork",
    "SQLAlchemyEventStore",
    "SQLAlchemyOutboxStorage",
    "Base",
    "OutboxMessage",
    "StoredEventModel",
    "OutboxStatus",
    # Specifications / Compiler
    "build_sqla_filter",
    "apply_query_options",
    "SQLAlchemyOperator",
    "SQLAlchemyOperatorRegistry",
    "SQLAlchemyResolutionContext",
    "SQLAlchemyHookResult",
    # Exceptions
    "SQLAlchemyPersistenceError",
    "SessionManagementError",
    "UnitOfWorkError",
    "RepositoryError",
    "TransactionError",
    "OptimisticConcurrencyError",
    "MappingError",
]
