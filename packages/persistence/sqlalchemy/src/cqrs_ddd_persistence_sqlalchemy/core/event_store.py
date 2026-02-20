"""
SQLAlchemy implementation of the Event Store.

Uses SQLAlchemy Sequence for auto-incremented ``position`` field,
ensuring atomicity and preventing race conditions without any migration logic.
"""

from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent

from .models import StoredEventModel


class SQLAlchemyEventStore(IEventStore):
    """
    Event Store implementation using SQLAlchemy.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(self, stored_event: StoredEvent) -> None:
        """
        Append a single stored event.

        Position is auto-incremented by database Sequence, ensuring
        atomicity and no race conditions.
        """
        model = StoredEventModel(
            event_id=stored_event.event_id,
            event_type=stored_event.event_type,
            aggregate_id=stored_event.aggregate_id,
            aggregate_type=stored_event.aggregate_type,
            version=stored_event.version,
            schema_version=stored_event.schema_version,
            payload=stored_event.payload,
            metadata_=stored_event.metadata,
            occurred_at=stored_event.occurred_at,
            correlation_id=stored_event.correlation_id,
            causation_id=stored_event.causation_id,
            # Position handled by Sequence - don't set manually
        )
        self.session.add(model)

    async def append_batch(self, events: list[StoredEvent]) -> None:
        """
        Append multiple stored events atomically.

        Positions are auto-incremented by database Sequence for each event.
        """
        models = [
            StoredEventModel(
                event_id=event.event_id,
                event_type=event.event_type,
                aggregate_id=event.aggregate_id,
                aggregate_type=event.aggregate_type,
                version=event.version,
                schema_version=event.schema_version,
                payload=event.payload,
                metadata_=event.metadata,
                occurred_at=event.occurred_at,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                # Position handled by Sequence - don't set manually
            )
            for event in events
        ]
        self.session.add_all(models)

    async def get_events(
        self,
        aggregate_id: str,
        *,
        after_version: int = 0,
    ) -> list[StoredEvent]:
        """
        Return events for an aggregate after *after_version*.
        """
        stmt = (
            select(StoredEventModel)
            .where(
                StoredEventModel.aggregate_id == aggregate_id,
                StoredEventModel.version > after_version,
            )
            .order_by(StoredEventModel.version)
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_dataclass(m) for m in models]

    async def get_by_aggregate(
        self,
        aggregate_id: str,
        aggregate_type: str | None = None,
    ) -> list[StoredEvent]:
        """
        Return all events for an aggregate, optionally filtered by type.
        """
        stmt = select(StoredEventModel).where(
            StoredEventModel.aggregate_id == aggregate_id
        )
        if aggregate_type:
            stmt = stmt.where(StoredEventModel.aggregate_type == aggregate_type)
        stmt = stmt.order_by(StoredEventModel.version)

        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_dataclass(m) for m in models]

    async def get_all(self) -> list[StoredEvent]:
        """
        Return every stored event (for projections / catch-up).

        For better performance with large event histories, use
        :meth:`get_events_after` or :meth:`get_all_streaming`.
        """
        stmt = select(StoredEventModel).order_by(StoredEventModel.occurred_at)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_dataclass(m) for m in models]

    async def get_events_after(
        self, position: int, limit: int = 1000
    ) -> list[StoredEvent]:
        """
        Return events after a given position for cursor-based pagination.

        Uses the ``position`` column for efficient pagination without loading
        all events into memory.
        """
        stmt = (
            select(StoredEventModel)
            .where(StoredEventModel.position > position)
            .order_by(StoredEventModel.position)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_dataclass(m) for m in models]

    async def get_all_streaming(
        self, batch_size: int = 1000
    ) -> AsyncIterator[list[StoredEvent]]:
        """
        Stream all events in batches for memory-efficient processing.

        Yields batches until all events are consumed. Uses the position
        field from StoredEvent for cursor-based iteration.
        """
        # Track offset manually for events without position (backward compatibility)
        offset = 0
        while True:
            batch = await self.get_events_after(offset, batch_size)
            if not batch:
                break
            yield batch
            # Update offset for next batch
            offset += len(batch)

    def _to_dataclass(self, model: StoredEventModel) -> StoredEvent:
        """
        Convert SQLAlchemy model to StoredEvent dataclass.

        Position is auto-generated by database Sequence, ensuring
        atomicity and no race conditions.
        """
        return StoredEvent(
            event_id=model.event_id,
            event_type=model.event_type,
            aggregate_id=model.aggregate_id,
            aggregate_type=model.aggregate_type,
            version=model.version,
            schema_version=getattr(model, "schema_version", 1),
            payload=model.payload,
            metadata=model.metadata_,
            occurred_at=model.occurred_at,
            correlation_id=model.correlation_id,
            causation_id=model.causation_id,
            position=model.position,
        )
