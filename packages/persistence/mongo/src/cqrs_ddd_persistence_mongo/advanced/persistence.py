"""
MongoDB concrete bases for the advanced persistence dispatcher.

These abstract bases provide the MongoDB-aware scaffolding for the four
persistence roles:

- ``MongoOperationPersistence`` — command-side writes
- ``MongoRetrievalPersistence`` — command-side reads (aggregate retrieval)
- ``MongoQueryPersistence`` — ID-based query-side reads
- ``MongoQuerySpecificationPersistence`` — specification-based query reads

Each base optionally resolves a MongoDB session from the UnitOfWork
for transactional consistency, and uses the serialization helpers
(`model_to_doc` / `model_from_doc`) for entity ↔ document conversion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from uuid import UUID

from cqrs_ddd_advanced_core.ports.persistence import (
    IOperationPersistence,
    IQueryPersistence,
    IQuerySpecificationPersistence,
    IRetrievalPersistence,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.ports.search_result import SearchResult

from ..core.session_utils import session_in_transaction
from ..core.uow import MongoUnitOfWork
from ..exceptions import MongoPersistenceError
from ..query_builder import MongoQueryBuilder
from ..search_helpers import extract_search_context, normalise_criteria
from ..serialization import model_from_doc, model_to_doc

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from ..connection import MongoConnectionManager

T_Entity = TypeVar("T_Entity", bound=AggregateRoot[Any])
T_Result = TypeVar("T_Result")
T_ID = TypeVar("T_ID", str, int, UUID)


def _session_from(uow: UnitOfWork | None) -> Any:
    """Extract MongoDB session from a UnitOfWork, if available.

    Args:
        uow: Optional UnitOfWork.

    Returns:
        MongoDB session or None.
    """
    if uow is not None and isinstance(uow, MongoUnitOfWork):
        return uow.session
    return None


# ---------------------------------------------------------------------------
# Operation (Write) base
# ---------------------------------------------------------------------------


class MongoOperationPersistence(
    IOperationPersistence[T_Entity, T_ID],
    ABC,
    Generic[T_Entity, T_ID],
):
    """
    Abstract base for persisting aggregate modifications via MongoDB.

    Subclasses must define:
        - ``connection``: MongoConnectionManager instance
        - ``collection_name``: Name of the collection
        - ``id_field``: Name of the ID field (default: "id")

    Uses ``model_to_doc`` for entity → document conversion.
    """

    connection: MongoConnectionManager
    collection_name: str
    id_field: str = "id"
    database: str | None = None

    def _db(self) -> Any:
        """Get the database instance."""
        client = self.connection.client
        database_name = self.database or getattr(self.connection, "_database", None)
        if database_name:
            try:
                return client.get_database(database_name)
            except TypeError:
                return client.get_database(name=database_name)
        try:
            return client.get_database()
        except Exception as e:
            raise MongoPersistenceError(
                "Database name must be set when using mongomock or when "
                "client has no default database"
            ) from e

    def _collection(self) -> Any:
        """Get the MongoDB collection."""
        return self._db()[self.collection_name]

    async def persist(
        self,
        entity: T_Entity,
        uow: UnitOfWork | None = None,
        events: list[DomainEvent] | None = None,  # noqa: ARG002
    ) -> T_ID:
        """
        Persist the entity.

        For transactional consistency, provide a MongoUnitOfWork.

        Args:
            entity: The aggregate to persist.
            uow: Optional UnitOfWork for transactional context.
            events: Optional domain events (not used in this implementation,
                   events flow via middleware).

        Returns:
            The entity ID.
        """
        coll = self._collection()
        session = _session_from(uow)
        doc = model_to_doc(entity, use_id_field=self.id_field)

        doc_id = doc.get("_id")
        if not doc_id:
            from uuid import uuid4

            doc_id = str(uuid4())
        doc["_id"] = doc_id

        if session and session_in_transaction(session):
            # Insert/replace within transaction
            try:
                await coll.replace_one(
                    {"_id": doc_id}, doc, upsert=True, session=session
                )
            except (NotImplementedError, TypeError):
                # mongomock doesn't support sessions
                await coll.replace_one({"_id": doc_id}, doc, upsert=True)
        else:
            # Insert/replace without transaction
            await coll.replace_one({"_id": doc_id}, doc, upsert=True)

        return str(doc_id)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Retrieval (command-side read) base
# ---------------------------------------------------------------------------


class MongoRetrievalPersistence(
    IRetrievalPersistence[T_Entity, T_ID],
    ABC,
    Generic[T_Entity, T_ID],
):
    """
    Abstract base for retrieving aggregates by ID.

    Subclasses must define:
        - ``connection``: MongoConnectionManager instance
        - ``collection_name``: Name of the collection
        - ``model_cls``: The aggregate class to hydrate
        - ``id_field``: Name of the ID field (default: "id")
    """

    connection: MongoConnectionManager
    collection_name: str
    model_cls: type[T_Entity]
    id_field: str = "id"
    database: str | None = None

    def _db(self) -> Any:
        """Get the database instance."""
        client = self.connection.client
        database_name = self.database or getattr(self.connection, "_database", None)
        if database_name:
            try:
                return client.get_database(database_name)
            except TypeError:
                return client.get_database(name=database_name)
        try:
            return client.get_database()
        except Exception as e:
            raise MongoPersistenceError(
                "Database name must be set when using mongomock or when "
                "client has no default database"
            ) from e

    def _collection(self) -> Any:
        """Get the MongoDB collection."""
        return self._db()[self.collection_name]

    async def retrieve(
        self, ids: Sequence[T_ID], uow: UnitOfWork | None = None
    ) -> list[T_Entity]:
        """
        Retrieve aggregates by their IDs.

        Args:
            ids: List of entity IDs to retrieve.
            uow: Optional UnitOfWork (session not typically used for reads,
                  but kept for interface consistency).

        Returns:
            List of hydrated aggregate instances.
        """
        coll = self._collection()
        session = _session_from(uow)

        filter_query = {"_id": {"$in": list(ids)}}

        if session:
            try:
                cursor = coll.find(filter_query, session=session)
            except (NotImplementedError, TypeError):
                # mongomock doesn't support sessions
                cursor = coll.find(filter_query)
        else:
            cursor = coll.find(filter_query)

        entities = []
        async for doc in cursor:
            entity = model_from_doc(self.model_cls, doc, id_field=self.id_field)
            entities.append(entity)

        return entities


# ---------------------------------------------------------------------------
# Query (ID-based read model) base
# ---------------------------------------------------------------------------


class MongoQueryPersistence(
    IQueryPersistence[T_Result, T_ID],
    ABC,
    Generic[T_Result, T_ID],
):
    """
    Abstract base for ID-based query-side persistence (Read Models).

    Subclasses must define:
        - ``connection``: MongoConnectionManager instance
        - ``collection_name``: Name of the collection
        - ``to_dto``: Abstract method to convert document → DTO
    """

    connection: MongoConnectionManager
    collection_name: str
    database: str | None = None

    def _db(self) -> Any:
        """Get the database instance."""
        client = self.connection.client
        database_name = self.database or getattr(self.connection, "_database", None)
        if database_name:
            try:
                return client.get_database(database_name)
            except TypeError:
                return client.get_database(name=database_name)
        try:
            return client.get_database()
        except Exception as e:
            raise MongoPersistenceError(
                "Database name must be set when using mongomock or when "
                "client has no default database"
            ) from e

    def _collection(self) -> Any:
        """Get the MongoDB collection."""
        return self._db()[self.collection_name]

    @abstractmethod
    def to_dto(self, doc: dict[str, Any]) -> T_Result:
        """Convert a MongoDB document to a result DTO.

        Args:
            doc: The document from MongoDB.

        Returns:
            The hydrated DTO instance.
        """
        ...

    async def fetch(
        self, ids: Sequence[T_ID], uow: UnitOfWork | None = None
    ) -> list[T_Result]:
        """
        Fetch result DTOs by their IDs.

        Args:
            ids: List of entity IDs to fetch.
            uow: Optional UnitOfWork (session not typically used for reads).

        Returns:
            List of DTO instances.
        """
        coll = self._collection()
        session = _session_from(uow)

        filter_query = {"_id": {"$in": list(ids)}}

        if session:
            try:
                cursor = coll.find(filter_query, session=session)
            except (NotImplementedError, TypeError):
                # mongomock doesn't support sessions
                cursor = coll.find(filter_query)
        else:
            cursor = coll.find(filter_query)

        dtos = []
        async for doc in cursor:
            dto = self.to_dto(doc)
            dtos.append(dto)

        return dtos


# ---------------------------------------------------------------------------
# Query Specification (spec-based read model) base
# ---------------------------------------------------------------------------


class MongoQuerySpecificationPersistence(
    IQuerySpecificationPersistence[T_Result],
    ABC,
    Generic[T_Result],
):
    """
    Abstract base for Specification-based query-side persistence (Read Models).

    Subclasses must define:
        - ``connection``: MongoConnectionManager instance
        - ``collection_name``: Name of the collection
        - ``to_dto``: Abstract method to convert document → DTO
        - ``query_builder``: Optional MongoQueryBuilder instance

    Supports both ``ISpecification`` and ``QueryOptions`` as criteria.
    Returns a ``SearchResult[T_Result]`` for batch or streaming access.
    """

    connection: MongoConnectionManager
    collection_name: str
    database: str | None = None
    query_builder: MongoQueryBuilder | None = None

    def __init__(self) -> None:
        """Initialize the query persistence base."""
        if not hasattr(self, "query_builder") or self.query_builder is None:
            self.query_builder = MongoQueryBuilder()

    def _db(self) -> Any:
        """Get the database instance."""
        client = self.connection.client
        database_name = self.database or getattr(self.connection, "_database", None)
        if database_name:
            try:
                return client.get_database(database_name)
            except TypeError:
                return client.get_database(name=database_name)
        try:
            return client.get_database()
        except Exception as e:
            raise MongoPersistenceError(
                "Database name must be set when using mongomock or when "
                "client has no default database"
            ) from e

    def _collection(self) -> Any:
        """Get the MongoDB collection."""
        return self._db()[self.collection_name]

    @abstractmethod
    def to_dto(self, doc: dict[str, Any]) -> T_Result:
        """Convert a MongoDB document to a result DTO.

        Args:
            doc: The document from MongoDB.

        Returns:
            The hydrated DTO instance.
        """
        ...

    def fetch(
        self,
        criteria: ISpecification[Any] | Any,
        uow: UnitOfWork,  # Match protocol signature (non-optional)  # noqa: ARG002
    ) -> SearchResult[T_Result]:
        """
        Fetch result DTOs by specification or QueryOptions.

        Args:
            criteria: An ``ISpecification`` or ``QueryOptions`` instance.
            uow: UnitOfWork (session not typically used for reads but
            required by protocol).

        Returns:
            A ``SearchResult`` supporting both batch and streaming access.
        """
        spec, options = normalise_criteria(criteria)

        # Build MongoDB query from specification
        if self.query_builder is None:
            self.query_builder = MongoQueryBuilder()

        # Extract context from both spec and options
        order_by, limit, offset, fields = extract_search_context(spec, options)

        # Build query components
        filter_query = self.query_builder.build_match(spec) if spec else {}
        sort = self.query_builder.build_sort(
            order_by if isinstance(order_by, list) else None
        )
        skip = offset

        coll = self._collection()

        # Function to create cursor with options
        def _create_cursor() -> Any:
            """Create a new cursor with filter and options."""
            cursor = coll.find(filter_query)
            if sort:
                cursor = cursor.sort(sort)
            if skip is not None:
                cursor = cursor.skip(skip)
            if limit is not None:
                cursor = cursor.limit(limit)
            return cursor

        # Create result object for batch retrieval
        async def _as_list() -> list[T_Result]:
            """Fetch all results as a list."""
            results = []
            cursor = _create_cursor()
            async for doc in cursor:
                dto = self.to_dto(doc)
                results.append(dto)
            return results

        # Create async iterator for streaming
        async def _stream(_batch_size: int | None = None) -> AsyncIterator[T_Result]:
            """Stream results as an async iterator.

            Args:
                _batch_size: Batch size hint (not used for MongoDB cursor).

            Yields:
                DTO instances one by one.
            """
            cursor = _create_cursor()
            async for doc in cursor:
                dto = self.to_dto(doc)
                yield dto

        return SearchResult(_as_list, _stream)
