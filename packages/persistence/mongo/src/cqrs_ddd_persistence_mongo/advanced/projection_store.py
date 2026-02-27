"""MongoDB projection store implementing IProjectionWriter and IProjectionReader."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from cqrs_ddd_advanced_core.ports.projection import (
    DocId,
    IProjectionReader,
    IProjectionWriter,
)

from ..exceptions import MongoPersistenceError

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.projections.schema import ProjectionSchema
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from ..connection import MongoConnectionManager

logger = logging.getLogger("cqrs_ddd.projection.mongo")


def _get_client_and_db(
    client: Any = None,
    database: str | None = None,
    connection: MongoConnectionManager | None = None,
) -> tuple[Any, str]:
    if client is not None and database is not None:
        return client, database
    if connection is not None:
        db = database or getattr(connection, "_database", None)
        if db is None:
            raise MongoPersistenceError(
                "Database name must be set when using MongoConnectionManager"
            )
        return connection.client, db
    raise MongoPersistenceError(
        "Provide (client, database) or (connection=..., database=...)"
    )


class MongoProjectionStore(IProjectionWriter, IProjectionReader):
    """
    MongoDB implementation of IProjectionWriter and IProjectionReader.

    Features:
    - Version-based concurrency control (optimistic locking)
    - Idempotent event processing via _last_event_id
    - Efficient batch upserts using bulk_write
    - Flexible ID field mapping

    Supports (client, database) or (connection, database=...) for construction.
    Uses UnitOfWork.session when provided for transaction support.
    """

    def __init__(
        self,
        client: Any = None,
        database: str | None = None,
        *,
        connection: MongoConnectionManager | None = None,
        id_field: str = "id",
    ) -> None:
        self._client, self._database = _get_client_and_db(
            client=client, database=database, connection=connection
        )
        self._id_field = id_field

    def _db(self) -> Any:
        try:
            return self._client.get_database(self._database)
        except TypeError:
            return self._client.get_database(name=self._database)

    def _coll(self, name: str) -> Any:
        return self._db()[name]

    def _get_session(self, uow: UnitOfWork | None) -> Any:
        if uow is None:
            return None
        return getattr(uow, "session", None)

    def _normalize_doc_id(self, doc_id: DocId) -> dict[str, Any]:
        if isinstance(doc_id, (str, int)):
            return {"_id": doc_id}
        if isinstance(doc_id, dict):
            return dict(doc_id)
        raise ValueError(f"Invalid doc_id type: {type(doc_id)}")

    async def get(
        self,
        collection: str,
        doc_id: DocId,
        *,
        uow: UnitOfWork | None = None,
    ) -> dict[str, Any] | None:
        session = self._get_session(uow)
        filter_doc = self._normalize_doc_id(doc_id)
        if "_id" not in filter_doc and "id" in filter_doc:
            filter_doc["_id"] = filter_doc.get("id")
        doc = await self._coll(collection).find_one(filter_doc, session=session)
        if doc is None:
            return None
        return dict(doc)

    async def get_batch(
        self,
        collection: str,
        doc_ids: list[DocId],
        *,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any] | None]:
        """Fetch multiple documents by IDs, preserving order."""
        if not doc_ids:
            return []

        session = self._get_session(uow)
        coll = self._coll(collection)

        results: list[dict[str, Any] | None] = [None] * len(doc_ids)

        # Build filter for all IDs
        if all(isinstance(d, (str, int)) for d in doc_ids):
            filter_doc = {"_id": {"$in": list(doc_ids)}}
            cursor = coll.find(filter_doc, session=session)
            rows_by_id = {}
            async for doc in cursor:
                rows_by_id[doc["_id"]] = dict(doc)

            # Map back to original order
            for i, doc_id in enumerate(doc_ids):
                results[i] = rows_by_id.get(doc_id)
        else:
            # Fallback: individual queries for composite keys
            for i, doc_id in enumerate(doc_ids):
                results[i] = await self.get(collection, doc_id, uow=uow)

        return results

    async def find(
        self,
        collection: str,
        filter: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any]]:
        """Query documents by filter dict."""
        session = self._get_session(uow)
        coll = self._coll(collection)
        cursor = coll.find(filter, session=session).skip(offset).limit(limit)
        results = []
        async for doc in cursor:
            results.append(dict(doc))
        return results

    async def ensure_collection(
        self,
        collection: str,
        *,
        schema: ProjectionSchema | None = None,
    ) -> None:
        """MongoDB auto-creates collections; no-op (or optional validation from schema)."""

    async def collection_exists(self, collection: str) -> bool:
        names = await self._db().list_collection_names()
        return collection in names

    async def truncate_collection(self, collection: str) -> None:
        await self._coll(collection).delete_many({})

    async def drop_collection(self, collection: str) -> None:
        await self._coll(collection).drop()

    async def upsert(
        self,
        collection: str,
        doc_id: DocId,
        data: dict[str, Any] | Any,
        *,
        event_position: int | None = None,
        event_id: str | None = None,
        uow: UnitOfWork | None = None,
    ) -> bool:
        session = self._get_session(uow)
        coll = self._coll(collection)
        filter_doc = self._normalize_doc_id(doc_id)
        if "_id" not in filter_doc and "id" in filter_doc:
            filter_doc["_id"] = filter_doc.get("id")

        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="python")
        data = dict(data)

        # Idempotency check: skip if we've already processed this event
        if event_id:
            existing = await coll.find_one(
                {"_last_event_id": event_id}, session=session
            )
            if existing:
                logger.debug(
                    "Skipping duplicate event %s for %s/%s",
                    event_id,
                    collection,
                    doc_id,
                )
                return False

        # Version check: skip if existing version is >= event_position
        if event_position is not None:
            existing = await coll.find_one(filter_doc, session=session)
            if existing:
                existing_version = existing.get("_version", 0)
                if existing_version >= event_position:
                    logger.debug(
                        "Skipping stale event at position %s (current: %s) for %s/%s",
                        event_position,
                        existing_version,
                        collection,
                        doc_id,
                    )
                    return False
            data["_version"] = event_position
            data["_last_event_id"] = event_id
            data["_last_event_position"] = event_position

        if "_id" not in data and "_id" in filter_doc:
            data["_id"] = filter_doc["_id"]
        elif self._id_field in data and "_id" not in data:
            data["_id"] = data.pop(self._id_field)
        elif "id" in data and "_id" not in data:
            data["_id"] = data.get("id")
        # Remove id_field from doc when it was used as _id source (e.g. custom_id)
        if self._id_field in data and data.get("_id") is not None:
            data.pop(self._id_field, None)

        result = await coll.replace_one(filter_doc, data, upsert=True, session=session)
        return cast("bool", result.acknowledged)

    async def upsert_batch(
        self,
        collection: str,
        docs: list[dict[str, Any] | Any],
        *,
        id_field: str = "id",
        uow: UnitOfWork | None = None,
    ) -> None:
        """Bulk upsert using bulk_write for efficiency (single round trip).

        Falls back to individual replace_one operations for mongomock compatibility.
        """
        session = self._get_session(uow)
        coll = self._coll(collection)

        normalized_docs = []

        for item in docs:
            if hasattr(item, "model_dump"):
                doc = dict(item.model_dump(mode="python"))
            else:
                doc = dict(item)

            doc_id = doc.pop(id_field, doc.get("_id"))
            if doc_id is None:
                raise MongoPersistenceError("Each document must have an id")

            doc["_id"] = doc_id
            normalized_docs.append(doc)

        if not normalized_docs:
            return

        # Try bulk_write first (more efficient with real MongoDB)
        try:
            from pymongo import ReplaceOne

            bulk_ops = [
                ReplaceOne({"_id": doc["_id"]}, doc, upsert=True)
                for doc in normalized_docs
            ]
            await coll.bulk_write(bulk_ops, session=session)
        except (NotImplementedError, AttributeError, TypeError) as e:
            # Fallback for mongomock which doesn't fully support bulk_write
            # TypeError occurs when mongomock's BulkOperationBuilder doesn't support
            # newer pymongo ReplaceOne arguments (e.g., 'sort' parameter)
            logger.debug(
                "bulk_write not supported (%s), falling back to individual ops", e
            )
            for doc in normalized_docs:
                await coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def delete(
        self,
        collection: str,
        doc_id: DocId,
        *,
        cascade: bool = False,
        uow: UnitOfWork | None = None,
    ) -> None:
        session = self._get_session(uow)
        filter_doc = self._normalize_doc_id(doc_id)
        await self._coll(collection).delete_one(filter_doc, session=session)

    async def ensure_ttl_index(
        self,
        collection: str,
        field: str,
        expire_after_seconds: int,
    ) -> None:
        await self._coll(collection).create_index(
            [(field, 1)],
            expireAfterSeconds=expire_after_seconds,
            name=f"ttl_{field}",
        )
