"""MongoDB implementation of ISnapshotStore."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cqrs_ddd_advanced_core.ports.snapshots import ISnapshotStore

from ..exceptions import MongoPersistenceError


def _doc_id(aggregate_type: str, aggregate_id: Any) -> str:
    return f"{aggregate_type}|{aggregate_id}"


def _get_client_and_db(
    client: Any = None,
    database: str | None = None,
    connection: Any = None,
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


class MongoSnapshotStore(ISnapshotStore):
    """
    MongoDB implementation of ISnapshotStore.

    Uses a dedicated collection (default "snapshots"). Document id:
    {aggregate_type}|{aggregate_id}. Saves snapshot_data, version, created_at.
    """

    COLLECTION = "snapshots"

    def __init__(
        self,
        client: Any = None,
        database: str | None = None,
        *,
        connection: MongoConnectionManager | None = None,
        collection: str | None = None,
    ) -> None:
        self._client, self._database = _get_client_and_db(
            client=client, database=database, connection=connection
        )
        self._collection_name = collection or self.COLLECTION

    def _coll(self):
        return self._client[self._database][self._collection_name]

    async def save_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        snapshot_data: dict[str, Any],
        version: int,
    ) -> None:
        doc_id = _doc_id(aggregate_type, aggregate_id)
        now = datetime.now(timezone.utc)
        doc = {
            "_id": doc_id,
            "snapshot_data": snapshot_data,
            "version": version,
            "created_at": now,
        }
        await self._coll().replace_one(
            {"_id": doc_id},
            doc,
            upsert=True,
        )

    async def get_latest_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
    ) -> dict[str, Any] | None:
        doc_id = _doc_id(aggregate_type, aggregate_id)
        doc = await self._coll().find_one({"_id": doc_id})
        if doc is None:
            return None
        return {
            "snapshot_data": doc["snapshot_data"],
            "version": doc["version"],
            "created_at": doc["created_at"],
        }

    async def delete_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
    ) -> None:
        doc_id = _doc_id(aggregate_type, aggregate_id)
        await self._coll().delete_one({"_id": doc_id})
