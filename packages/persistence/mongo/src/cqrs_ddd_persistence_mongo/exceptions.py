"""MongoDB persistence exceptions."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import PersistenceError


class MongoPersistenceError(PersistenceError):
    """Base for MongoDB persistence errors."""


class MongoConnectionError(MongoPersistenceError):
    """Raised when connection to MongoDB fails."""


class MongoQueryError(MongoPersistenceError):
    """Raised when a query or compilation fails."""
