"""
SQLAlchemy implementation of the Event Store.
"""

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
        """
        model = StoredEventModel(
            event_id=stored_event.event_id,
            event_type=stored_event.event_type,
            aggregate_id=stored_event.aggregate_id,
            aggregate_type=stored_event.aggregate_type,
            version=stored_event.version,
            payload=stored_event.payload,
            metadata_=stored_event.metadata,
            occurred_at=stored_event.occurred_at,
            correlation_id=stored_event.correlation_id,
            causation_id=stored_event.causation_id,
        )
        self.session.add(model)

    async def append_batch(self, events: list[StoredEvent]) -> None:
        """
        Append multiple stored events atomically.
        """
        models = [
            StoredEventModel(
                event_id=event.event_id,
                event_type=event.event_type,
                aggregate_id=event.aggregate_id,
                aggregate_type=event.aggregate_type,
                version=event.version,
                payload=event.payload,
                metadata_=event.metadata,
                occurred_at=event.occurred_at,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
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
        """
        stmt = select(StoredEventModel).order_by(StoredEventModel.occurred_at)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_dataclass(m) for m in models]

    def _to_dataclass(self, model: StoredEventModel) -> StoredEvent:
        return StoredEvent(
            event_id=model.event_id,
            event_type=model.event_type,
            aggregate_id=model.aggregate_id,
            aggregate_type=model.aggregate_type,
            version=model.version,
            payload=model.payload,
            metadata=model.metadata_,
            occurred_at=model.occurred_at,
            correlation_id=model.correlation_id,
            causation_id=model.causation_id,
        )
