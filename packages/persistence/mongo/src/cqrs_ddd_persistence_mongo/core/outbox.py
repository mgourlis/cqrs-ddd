"""
MongoDB implementation of the transactional outbox storage.

Stores messages in the same database (different collection) for atomic
consistency within the same transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.outbox import IOutboxStorage, OutboxMessage
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

from ..exceptions import MongoPersistenceError
from .session_utils import session_in_transaction

if TYPE_CHECKING:
    from ..connection import MongoConnectionManager


class MongoOutboxStorage(IOutboxStorage):
    """
    Transactional outbox storage implementation using MongoDB.

    Stores messages in an ``outbox_messages`` collection with the schema:
        {
            "_id": message_id,
            "event_type": str,
            "payload": dict,
            "metadata": dict,
            "status": "pending" | "published" | "failed",
            "created_at": datetime,
            "published_at": datetime | None,
            "retry_count": int,
            "error": str | None,
            "correlation_id": str,
            "causation_id": str | None
        }

    The outbox can be used with a Unit of Work to ensure atomic
    message persistence within the same transaction as aggregate changes.
    """

    COLLECTION = "outbox_messages"

    def __init__(
        self,
        connection: MongoConnectionManager,
        database: str | None = None,
    ) -> None:
        """
        Initialize outbox storage.

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
        """Get the outbox messages collection."""
        return self._db()[self.COLLECTION]

    def _extract_session(self, uow: UnitOfWork | None) -> Any:
        """Extract MongoDB session from Unit of Work if available.

        Args:
            uow: Optional Unit of Work containing a MongoUnitOfWork.

        Returns:
            MongoDB session or None.
        """
        if uow is not None and hasattr(uow, "session"):
            return uow.session
        return None

    async def save_messages(
        self,
        messages: list[OutboxMessage],
        uow: UnitOfWork | None = None,
    ) -> None:
        """
        Persist outbox messages in the same transaction as the aggregate changes.

        Args:
            messages: Messages to save to outbox.
            uow: Optional Unit of Work for transactional consistency.
                 If provided and contains a MongoUnitOfWork, messages are
                 inserted within the same transaction.
        """
        coll = self._collection()
        session = self._extract_session(uow)

        docs = []
        for msg in messages:
            doc = {
                "_id": msg.message_id,
                "event_type": msg.event_type,
                "payload": msg.payload,
                "metadata": msg.metadata,
                "status": "pending",
                "created_at": msg.created_at,
                "published_at": None,
                "retry_count": msg.retry_count,
                "error": msg.error,
                "correlation_id": msg.correlation_id,
                "causation_id": msg.causation_id,
            }
            docs.append(doc)

        if session and session_in_transaction(session):
            # Insert within transaction
            await coll.insert_many(docs, session=session)
        else:
            # Insert without transaction
            await coll.insert_many(docs)

    async def get_pending(
        self,
        limit: int = 100,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> list[OutboxMessage]:
        """
        Retrieve unpublished messages, ordered by creation time.

        Args:
            limit: Maximum number of messages to retrieve.
            uow: Optional Unit of Work (unused for reads).

        Returns:
            List of pending OutboxMessage instances.
        """
        coll = self._collection()
        cursor = coll.find({"status": "pending"}).sort("created_at", 1).limit(limit)
        messages = []

        async for doc in cursor:
            message = OutboxMessage(
                message_id=doc["_id"],
                event_type=doc["event_type"],
                payload=doc["payload"],
                metadata=doc.get("metadata", {}),
                created_at=doc["created_at"],
                published_at=doc.get("published_at"),
                error=doc.get("error"),
                retry_count=doc.get("retry_count", 0),
                correlation_id=doc.get("correlation_id", ""),
                causation_id=doc.get("causation_id"),
            )
            messages.append(message)

        return messages

    async def mark_published(
        self,
        message_ids: list[str],
        uow: UnitOfWork | None = None,
    ) -> None:
        """
        Mark messages as successfully published.

        Args:
            message_ids: IDs of messages to mark as published.
            uow: Optional Unit of Work for transactional consistency.
        """
        if not message_ids:
            return
        coll = self._collection()
        session = self._extract_session(uow)
        published_at = datetime.now(timezone.utc)
        update = {
            "$set": {
                "status": "published",
                "published_at": published_at,
            }
        }
        filter_query = {"_id": {"$in": message_ids}}
        if session and session_in_transaction(session):
            try:
                await coll.update_many(filter_query, update, session=session)
            except (NotImplementedError, TypeError):
                await coll.update_many(filter_query, update)
        else:
            await coll.update_many(filter_query, update)


    async def mark_failed(
        self,
        message_id: str,
        error: str,
        uow: UnitOfWork | None = None,
    ) -> None:
        """
        Record a publication failure for retry logic.

        Args:
            message_id: ID of the failed message.
            error: Error description.
            uow: Optional Unit of Work for transactional consistency.
        """
        coll = self._collection()
        session = self._extract_session(uow)

        result = coll.update_one(
            {"_id": message_id},
            {
                "$set": {"status": "failed", "error": error},
                "$inc": {"retry_count": 1},
            },
            session=session,
        )
        await result
