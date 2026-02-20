"""MongoProjectionStore — bulk upsert, drop_collection, TTL indexes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .exceptions import MongoPersistenceError

if TYPE_CHECKING:
    from .connection import MongoConnectionManager


class MongoProjectionStore:
    """Specialized store for projection workers.

    Supports upsert, batch upsert, collection reset, and TTL indexes.
    """

    def __init__(
        self,
        connection: MongoConnectionManager,
        database: str | None = None,
        *,
        id_field: str = "id",
    ) -> None:
        self._connection = connection
        self._database_name = database
        self._id_field = id_field

    def _db(self) -> Any:
        client = self._connection.client
        return (
            client.get_database(self._database_name)
            if self._database_name
            else client.get_database()
        )

    def _coll(self, collection: str) -> Any:
        return self._db()[collection]

    async def upsert(
        self,
        collection: str,
        doc_id: str,
        data: dict[str, Any] | Any,
        *,
        id_field: str | None = None,
    ) -> None:
        """Upsert a single document by id."""
        id_key = id_field or self._id_field
        if hasattr(data, "model_dump"):
            doc = data.model_dump(mode="json")
        else:
            doc = dict(data)
        doc["_id"] = doc.pop(id_key, doc_id)
        coll = self._coll(collection)
        await coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def upsert_batch(
        self,
        collection: str,
        docs: list[dict[str, Any] | Any],
        *,
        id_field: str | None = None,
    ) -> None:
        """Efficiently upsert multiple documents."""
        id_key = id_field or self._id_field
        coll = self._coll(collection)
        for item in docs:
            if hasattr(item, "model_dump"):
                doc = dict(item.model_dump(mode="json"))
            else:
                doc = dict(item)
            doc_id = doc.get(id_key, doc.get("_id"))
            if doc_id is None:
                raise MongoPersistenceError("Each document must have an id")
            doc["_id"] = doc_id
            if id_key != "_id" and id_key in doc:
                del doc[id_key]
            await coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def drop_collection(self, collection: str) -> None:
        """Drop the collection (for full replay)."""
        coll = self._coll(collection)
        await coll.drop()

    async def ensure_ttl_index(
        self, collection: str, field: str, expire_after_seconds: int
    ) -> None:
        """Create or update a TTL index on the given field."""
        coll = self._coll(collection)
        await coll.create_index(
            [(field, 1)],
            expireAfterSeconds=expire_after_seconds,
            name=f"ttl_{field}",
        )
