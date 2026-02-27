"""MongoDB persistence for CQRS/DDD.

Includes core persistence components (Repository, UnitOfWork, Outbox, EventStore,
CheckpointStore) and advanced persistence bases for dispatcher integration.
"""

from __future__ import annotations

# Advanced persistence bases for dispatcher integration
from .advanced.persistence import (
    MongoOperationPersistence,
    MongoQueryPersistence,
    MongoQuerySpecificationPersistence,
    MongoRetrievalPersistence,
)
from .advanced.position_store import MongoProjectionPositionStore
from .advanced.projection_store import MongoProjectionStore
from .advanced.snapshots import MongoSnapshotStore

# Core components
from .connection import MongoConnectionManager
from .core.checkpoint_store import MongoCheckpointStore
from .core.event_store import MongoEventStore
from .core.outbox import MongoOutboxStorage
from .core.repository import MongoRepository
from .core.uow import MongoUnitOfWork, MongoUnitOfWorkError
from .exceptions import (
    MongoConnectionError,
    MongoPersistenceError,
    MongoQueryError,
)
from .query_builder import MongoQueryBuilder
from .serialization import model_from_doc, model_to_doc

__all__ = [
    # Core
    "MongoConnectionManager",
    "MongoRepository",
    "MongoUnitOfWork",
    "MongoUnitOfWorkError",
    "MongoOutboxStorage",
    "MongoEventStore",
    "MongoCheckpointStore",
    "MongoProjectionPositionStore",
    "MongoProjectionStore",
    # Advanced
    "MongoOperationPersistence",
    "MongoRetrievalPersistence",
    "MongoQueryPersistence",
    "MongoQuerySpecificationPersistence",
    "MongoSnapshotStore",
    # Utilities
    "MongoQueryBuilder",
    "model_from_doc",
    "model_to_doc",
    # Exceptions
    "MongoPersistenceError",
    "MongoConnectionError",
    "MongoQueryError",
]
