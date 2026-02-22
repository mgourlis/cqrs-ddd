"""Advanced MongoDB persistence bases for dispatcher integration."""

from .jobs import MongoBackgroundJobRepository
from .persistence import (
    MongoOperationPersistence,
    MongoQueryPersistence,
    MongoQuerySpecificationPersistence,
    MongoRetrievalPersistence,
)
from .position_store import MongoProjectionPositionStore
from .projection_query import (
    MongoProjectionDualPersistence,
    MongoProjectionQueryPersistence,
    MongoProjectionSpecPersistence,
)
from .projection_store import MongoProjectionStore
from .saga import MongoSagaRepository
from .snapshots import MongoSnapshotStore

__all__ = [
    "MongoBackgroundJobRepository",
    "MongoOperationPersistence",
    "MongoProjectionPositionStore",
    "MongoProjectionStore",
    "MongoProjectionQueryPersistence",
    "MongoProjectionSpecPersistence",
    "MongoProjectionDualPersistence",
    "MongoRetrievalPersistence",
    "MongoQueryPersistence",
    "MongoQuerySpecificationPersistence",
    "MongoSagaRepository",
    "MongoSnapshotStore",
]
