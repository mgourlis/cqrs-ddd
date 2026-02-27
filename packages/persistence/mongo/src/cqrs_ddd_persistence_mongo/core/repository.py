"""MongoRepository[T] — generic read-model repository implementing IRepository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.ports.repository import IRepository
from cqrs_ddd_core.ports.search_result import SearchResult
from cqrs_ddd_core.primitives.exceptions import OptimisticConcurrencyError

from ..exceptions import MongoPersistenceError
from ..query_builder import MongoQueryBuilder
from ..search_helpers import extract_search_context, normalise_criteria
from .model_mapper import MongoDBModelMapper
from .session_utils import session_in_transaction
from .uow import MongoUnitOfWork

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from ..connection import MongoConnectionManager

T = TypeVar("T", bound=AggregateRoot[Any])


class MongoRepository(IRepository[T, str], Generic[T]):
    """Read-model repository over MongoDB. search() returns SearchResult[T]."""

    def __init__(
        self,
        connection: MongoConnectionManager,
        collection: str,
        model_cls: type[T],
        *,
        id_field: str = "id",
        query_builder: MongoQueryBuilder | None = None,
        database: str | None = None,
    ) -> None:
        self._connection = connection
        self._collection_name = collection
        self._model_cls = model_cls
        self._id_field = id_field
        self._query_builder = query_builder or MongoQueryBuilder()
        self._database = database
        self._mapper = MongoDBModelMapper(model_cls, id_field=id_field)

    def _db(self) -> Any:
        """Get the database instance."""
        database_name = self._database or getattr(self._connection, "_database", None)
        if not database_name:
            raise MongoPersistenceError(
                "Database name must be set on repository or connection"
            )
        return self._connection.client.get_database(database_name)

    def _collection(self, session: Any = None) -> Any:
        """Get the MongoDB collection, optionally with a session for
        transactions.
        """
        db = self._db()
        if session is None:
            return db.get_collection(self._collection_name)
        # Try to use session; fall back gracefully for mock clients
        # that don't support it
        try:
            return db.get_collection(self._collection_name, session=session)
        except TypeError:
            # mongomock doesn't support sessions
            return db.get_collection(self._collection_name)

    async def add(self, entity: T, uow: UnitOfWork | None = None) -> str:
        """Insert or replace document with optimistic concurrency check.
        Returns entity id.
        """
        session = uow.session if isinstance(uow, MongoUnitOfWork) else None
        coll = self._collection(session)
        doc = self._mapper.to_doc(entity)
        doc_id = doc.get("_id")
        if doc_id is None:
            from bson import ObjectId

            doc["_id"] = ObjectId()
            doc_id = str(doc["_id"])

        # Check if entity has version field for optimistic concurrency
        if hasattr(entity, "version"):
            expected_version = entity.version

            # Try atomic update with version check
            result = await coll.update_one(
                {
                    "_id": doc["_id"],
                    "version": expected_version,  # Conditional check
                },
                {
                    "$set": doc,
                    "$inc": {"version": 1},  # Atomic increment
                },
                upsert=False,
                session=session,
            )

            if result.matched_count == 0:
                # Document doesn't exist or version mismatch
                existing = await coll.find_one({"_id": doc["_id"]}, session=session)
                if existing:
                    raise OptimisticConcurrencyError(
                        f"Concurrent modification detected: expected version "
                        f"{expected_version}, but document has version "
                        f"{existing.get('version', 0)}"
                    )
                # Document doesn't exist, create it with version 1
                doc["version"] = 1
                await coll.insert_one(doc, session=session)
        else:
            # No versioning, simple upsert
            if session and session_in_transaction(session):
                # Try with session; fall back for mongomock which
                # doesn't support sessions
                try:
                    await coll.replace_one(
                        {"_id": doc["_id"]},
                        doc,
                        upsert=True,
                        session=session,
                    )
                except (NotImplementedError, TypeError):
                    # mongomock doesn't support sessions
                    await coll.replace_one(
                        {"_id": doc["_id"]},
                        doc,
                        upsert=True,
                    )
            else:
                await coll.replace_one(
                    {"_id": doc["_id"]},
                    doc,
                    upsert=True,
                )

        return str(doc_id)

    async def get(self, entity_id: str, uow: UnitOfWork | None = None) -> T | None:
        """Load one document by id."""
        session = uow.session if isinstance(uow, MongoUnitOfWork) else None
        coll = self._collection(session)
        doc = await coll.find_one({"_id": entity_id}, session=session)
        if doc is None:
            return None
        return self._mapper.from_doc(doc)

    async def delete(self, entity_id: str, uow: UnitOfWork | None = None) -> str:
        """Remove document by id. Returns deleted id."""
        session = uow.session if isinstance(uow, MongoUnitOfWork) else None
        coll = self._collection(session)
        if session and session_in_transaction(session):
            try:
                await coll.delete_one({"_id": entity_id}, session=session)
            except (NotImplementedError, TypeError):
                # mongomock doesn't support sessions
                await coll.delete_one({"_id": entity_id})
        else:
            await coll.delete_one({"_id": entity_id})
        return entity_id

    async def list_all(
        self,
        entity_ids: list[str] | None = None,
        uow: UnitOfWork | None = None,
    ) -> list[T]:
        """List documents; if entity_ids given, filter by _id in list."""
        session = uow.session if isinstance(uow, MongoUnitOfWork) else None
        coll = self._collection(session)
        if entity_ids:
            try:
                cursor = coll.find({"_id": {"$in": entity_ids}}, session=session)
            except (NotImplementedError, TypeError):
                # mongomock doesn't support sessions
                cursor = coll.find({"_id": {"$in": entity_ids}})
        else:
            try:
                cursor = coll.find({}, session=session)
            except (NotImplementedError, TypeError):
                # mongomock doesn't support sessions
                cursor = coll.find({})
        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results

    def _build_pipeline(
        self,
        *,
        match: dict[str, Any],
        sort_list: list[tuple[str, int]],
        offset: Any,
        limit: Any,
        fields: Any,
    ) -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = []
        if match:
            pipeline.append({"$match": match})
        if sort_list:
            pipeline.append({"$sort": dict(sort_list)})
        if offset is not None:
            pipeline.append({"$skip": offset})
        if limit is not None:
            pipeline.append({"$limit": limit})
        proj = self._query_builder.build_project(list(fields) if fields else None)
        if proj:
            pipeline.append({"$project": proj})
        return pipeline

    async def search(
        self,
        criteria: Any,
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T]:
        """Search with specification or query options.

        Returns :class:`SearchResult[T]` for both list and streaming access.
        """
        session = uow.session if isinstance(uow, MongoUnitOfWork) else None
        spec, options = normalise_criteria(criteria)
        match = self._query_builder.build_match(spec) if spec else {}
        order_by, limit, offset, fields = extract_search_context(spec, options)
        sort_list = self._query_builder.build_sort(
            order_by if isinstance(order_by, list) else None
        )

        async def list_fn() -> list[T]:
            coll = self._collection(session)
            pipeline = self._build_pipeline(
                match=match,
                sort_list=sort_list,
                offset=offset,
                limit=limit,
                fields=fields,
            )
            cursor = coll.aggregate(pipeline, session=session)
            return [self._mapper.from_doc(doc) async for doc in cursor]

        async def stream_fn(batch_size: int | None) -> AsyncIterator[T]:
            coll = self._collection(session)
            pipeline = self._build_pipeline(
                match=match,
                sort_list=sort_list,
                offset=offset,
                limit=limit,
                fields=fields,
            )
            batch = batch_size or 100
            cursor = coll.aggregate(pipeline, batchSize=batch, session=session)
            async for doc in cursor:
                yield self._mapper.from_doc(doc)

        return SearchResult(list_fn, stream_fn)
