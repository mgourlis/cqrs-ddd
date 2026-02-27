"""MongoCheckpointStore — ICheckpointStore for projection position tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from cqrs_ddd_projections.ports import ICheckpointStore

from ..exceptions import MongoPersistenceError

if TYPE_CHECKING:
    from ..connection import MongoConnectionManager


class MongoCheckpointStore(ICheckpointStore):
    """MongoDB implementation of ICheckpointStore for projection position tracking.

    Stores positions in a ``projection_checkpoints`` collection with the schema:
        {
            "_id": projection_name,  # primary key
            "position": int,
            "updated_at": datetime
        }

    Uses atomic ``replace_one`` with upsert to ensure thread-safe updates.
    """

    COLLECTION = "projection_checkpoints"

    def __init__(
        self,
        connection: MongoConnectionManager,
        database: str | None = None,
    ) -> None:
        """Initialize the checkpoint store.

        Args:
            connection: MongoDB connection manager.
            database: Optional database name. If None, uses client's default database.
        """
        self._connection = connection
        self._database_name = database

    def _db(self) -> Any:
        """Get the database instance.

        Mongomock requires positional argument, Motor accepts positional or keyword.
        This works with both."""
        client = self._connection.client
        database_name = self._database_name or getattr(
            self._connection, "_database", None
        )
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
        """Get the checkpoints collection."""
        return self._db()[self.COLLECTION]

    async def get_position(self, projection_name: str) -> int | None:
        """Retrieve checkpoint position from database.

        Args:
            projection_name: Unique identifier for the projection.

        Returns:
            Last processed position, or None if the projection has never run.
        """
        coll = self._collection()
        doc = await coll.find_one({"_id": projection_name})
        if doc is None:
            return None
        return cast("int | None", doc.get("position"))

    async def save_position(self, projection_name: str, position: int) -> None:
        """Save or update checkpoint position in database.

        Uses atomic upsert to ensure thread-safe updates.

        Args:
            projection_name: Unique identifier for the projection.
            position: The position to save (e.g., event sequence number).
        """
        coll = self._collection()
        await coll.replace_one(
            {"_id": projection_name},
            {
                "_id": projection_name,
                "position": position,
                "updated_at": datetime.now(timezone.utc),
            },
            upsert=True,
        )
