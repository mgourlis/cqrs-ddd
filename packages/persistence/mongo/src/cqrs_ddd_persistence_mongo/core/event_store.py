"""
MongoDB implementation of the Event Store.

Uses a separate counter collection for auto-incremented positions,
ensuring atomicity and preventing race conditions.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent

from ..exceptions import MongoPersistenceError

if TYPE_CHECKING:
    from ..connection import MongoConnectionManager

logger = logging.getLogger("cqrs_ddd.mongo.event_store")


class MongoEventStore(IEventStore):
    """
    Event Store implementation using MongoDB.

    Events are stored in the ``domain_events`` collection with schema:
        {
            "_id": event_id,
            "event_type": str,
            "aggregate_id": str,
            "aggregate_type": str,
            "version": int,
            "schema_version": int,
            "payload": dict,
            "metadata": dict,
            "occurred_at": datetime,
            "correlation_id": str | None,
            "causation_id": str | None,
            "position": int
        }

    Positions are auto-incremented using a separate ``counters`` collection
    with atomic ``find_one_and_update`` operations.
    """

    EVENTS_COLLECTION = "domain_events"
    COUNTERS_COLLECTION = "counters"
    POSITION_COUNTER = "domain_events_position"

    def __init__(
        self,
        connection: MongoConnectionManager,
        database: str | None = None,
    ) -> None:
        """
        Initialize event store.

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

    def _events_collection(self) -> Any:
        """Get the events collection."""
        return self._db()[self.EVENTS_COLLECTION]

    def _counters_collection(self) -> Any:
        """Get the counters collection."""
        return self._db()[self.COUNTERS_COLLECTION]

    async def _next_position(self) -> int:
        """
        Get the next position value atomically.

        Uses ``find_one_and_update`` with upsert to ensure
        thread-safe increment without race conditions.

        Returns:
            The next position value.
        """
        coll = self._counters_collection()
        result = await coll.find_one_and_update(
            {"_id": self.POSITION_COUNTER},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=True,
        )
        if result is None:
            # First time: counter was created with value=0, next is 1
            return 1
        return result["value"]

    def _stored_event_to_doc(self, event: StoredEvent) -> dict[str, Any]:
        """Convert StoredEvent to MongoDB document."""
        return {
            "_id": event.event_id,
            "event_type": event.event_type,
            "aggregate_id": event.aggregate_id,
            "aggregate_type": event.aggregate_type,
            "version": event.version,
            "schema_version": event.schema_version,
            "payload": event.payload,
            "metadata": event.metadata,
            "occurred_at": event.occurred_at,
            "correlation_id": event.correlation_id,
            "causation_id": event.causation_id,
            "position": event.position,
        }

    def _doc_to_stored_event(self, doc: dict[str, Any]) -> StoredEvent:
        """Convert MongoDB document to StoredEvent."""
        return StoredEvent(
            event_id=doc["_id"],
            event_type=doc["event_type"],
            aggregate_id=doc["aggregate_id"],
            aggregate_type=doc["aggregate_type"],
            version=doc["version"],
            schema_version=doc.get("schema_version", 1),
            payload=doc["payload"],
            metadata=doc.get("metadata", {}),
            occurred_at=doc["occurred_at"],
            correlation_id=doc.get("correlation_id"),
            causation_id=doc.get("causation_id"),
            position=doc.get("position"),
        )

    async def append(self, stored_event: StoredEvent) -> None:
        """
        Append a single stored event.

        Position is auto-incremented atomically via counter collection.

        Args:
            stored_event: The event to persist.
        """
        position = await self._next_position()
        event_with_position = StoredEvent(
            event_id=stored_event.event_id,
            event_type=stored_event.event_type,
            aggregate_id=stored_event.aggregate_id,
            aggregate_type=stored_event.aggregate_type,
            version=stored_event.version,
            schema_version=stored_event.schema_version,
            payload=stored_event.payload,
            metadata=stored_event.metadata,
            occurred_at=stored_event.occurred_at,
            correlation_id=stored_event.correlation_id,
            causation_id=stored_event.causation_id,
            position=position,
        )

        doc = self._stored_event_to_doc(event_with_position)
        coll = self._events_collection()
        await coll.insert_one(doc)

    async def append_batch(self, events: list[StoredEvent]) -> None:
        """
        Append multiple stored events atomically.

        Each event gets the next position via counter collection.

        Args:
            events: The events to persist.
        """
        if not events:
            return

        events_with_positions = []
        for event in events:
            position = await self._next_position()
            event_with_position = StoredEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                aggregate_id=event.aggregate_id,
                aggregate_type=event.aggregate_type,
                version=event.version,
                schema_version=event.schema_version,
                payload=event.payload,
                metadata=event.metadata,
                occurred_at=event.occurred_at,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                position=position,
            )
            events_with_positions.append(event_with_position)

        docs = [
            self._stored_event_to_doc(event) for event in events_with_positions
        ]
        coll = self._events_collection()
        await coll.insert_many(docs)

    async def get_events(
        self,
        aggregate_id: str,
        *,
        after_version: int = 0,
    ) -> list[StoredEvent]:
        """
        Return events for an aggregate after a given version.

        Args:
            aggregate_id: The aggregate ID.
            after_version: Only return events with version > after_version.

        Returns:
            List of StoredEvent instances.
        """
        coll = self._events_collection()
        filter_query = {"aggregate_id": aggregate_id, "version": {"$gt": after_version}}

        cursor = coll.find(filter_query).sort("version", 1)
        events = []

        async for doc in cursor:
            events.append(self._doc_to_stored_event(doc))

        return events

    async def get_by_aggregate(
        self,
        aggregate_id: str,
        aggregate_type: str | None = None,
    ) -> list[StoredEvent]:
        """
        Return all events for an aggregate, optionally filtered by type.

        Args:
            aggregate_id: The aggregate ID.
            aggregate_type: Optional aggregate type filter.

        Returns:
            List of StoredEvent instances.
        """
        coll = self._events_collection()
        filter_query = {"aggregate_id": aggregate_id}

        if aggregate_type is not None:
            filter_query["aggregate_type"] = aggregate_type

        cursor = coll.find(filter_query).sort("version", 1)
        events = []

        async for doc in cursor:
            events.append(self._doc_to_stored_event(doc))

        return events

    async def get_all(self) -> list[StoredEvent]:
        """
        Return every stored event.

        **Warning:** This can return a large number of events.
        Consider using ``get_events_after`` for pagination.

        Returns:
            List of all StoredEvent instances.
        """
        coll = self._events_collection()
        cursor = coll.find().sort("position", 1)
        events = []

        async for doc in cursor:
            events.append(self._doc_to_stored_event(doc))

        return events

    async def get_events_after(
        self, position: int, limit: int = 1000
    ) -> list[StoredEvent]:
        """
        Return events after a given position for cursor-based pagination.

        This is the preferred method for projections to avoid memory exhaustion.

        Args:
            position: The position to start from (exclusive).
            limit: Maximum number of events to return.

        Returns:
            List of StoredEvent instances.
        """
        coll = self._events_collection()
        cursor = (
            coll.find({"position": {"$gt": position}})
            .sort("position", 1)
            .limit(limit)
        )
        events = []

        async for doc in cursor:
            events.append(self._doc_to_stored_event(doc))

        return events

    def get_all_streaming(
        self, batch_size: int = 1000
    ) -> AsyncIterator[list[StoredEvent]]:
        """
        Stream all events in batches for memory-efficient processing.

        Satisfies IEventStore protocol. Yields batches of events in position order.

        Args:
            batch_size: Number of events per batch.

        Yields:
            Lists of StoredEvent instances.
        """

        async def _stream() -> AsyncIterator[list[StoredEvent]]:
            coll = self._events_collection()
            cursor = coll.find().sort("position", 1).batch_size(batch_size)
            batch: list[StoredEvent] = []
            async for doc in cursor:
                batch.append(self._doc_to_stored_event(doc))
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
            if batch:
                yield batch

        return _stream()

    async def get_events_from_position(
        self,
        position: int,
        *,
        limit: int | None = None,
    ) -> AsyncIterator[StoredEvent]:
        """
        Stream events starting from a given position (exclusive).

        Used by ProjectionWorker to resume after crash.
        """
        batch_size = limit if limit is not None else 1000
        current = position
        while True:
            batch = await self.get_events_after(current, batch_size)
            for e in batch:
                yield e
            if len(batch) < batch_size:
                break
            current = batch[-1].position if batch[-1].position is not None else current + len(batch)

    async def get_latest_position(self) -> int | None:
        """
        Get the highest event position in the store.

        Used for catch-up subscription mode.
        """
        coll = self._events_collection()
        doc = await coll.find_one(
            {},
            projection={"position": 1},
            sort=[("position", -1)],
        )
        return doc["position"] if doc else None

    async def stream_events(
        self, position: int = 0
    ) -> AsyncIterator[StoredEvent]:
        """
        Stream events starting from a given position.

        This is a memory-efficient alternative to ``get_all`` for
        processing large numbers of events (e.g., during projection replay).

        Args:
            position: The position to start from (exclusive).

        Yields:
            StoredEvent instances one by one.
        """
        coll = self._events_collection()
        cursor = coll.find({"position": {"$gt": position}}).sort("position", 1)

        async for doc in cursor:
            yield self._doc_to_stored_event(doc)
