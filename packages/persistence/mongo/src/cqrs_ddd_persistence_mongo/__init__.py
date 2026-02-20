"""MongoDB read-side persistence for CQRS/DDD.

Includes repository, query builder, and projection store.
"""

from __future__ import annotations

from .connection import MongoConnectionManager
from .exceptions import (
    MongoConnectionError,
    MongoPersistenceError,
    MongoQueryError,
)
from .projection_store import MongoProjectionStore
from .query_builder import MongoQueryBuilder
from .repository import MongoRepository
from .serialization import model_from_doc, model_to_doc

__all__ = [
    "MongoConnectionManager",
    "MongoPersistenceError",
    "MongoConnectionError",
    "MongoQueryError",
    "MongoProjectionStore",
    "MongoQueryBuilder",
    "MongoRepository",
    "model_from_doc",
    "model_to_doc",
]
