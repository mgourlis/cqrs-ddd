"""
SQLAlchemy implementation of the Event Store.

Uses SQLAlchemy Sequence for auto-incremented ``position`` field,
ensuring atomicity and preventing race conditions without any migration logic.

All read methods accept an optional ``specification`` parameter.  When
provided the specification is compiled to a SQLAlchemy WHERE clause via
:func:`build_sqla_filter` and composed with the base query.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent

from ..specifications.compiler import build_sqla_filter
from .models import StoredEventModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

    from cqrs_ddd_core.domain.specification import ISpecification


class SQLAlchemyEventStore(IEventStore):
    """
    Event Store implementation using SQLAlchemy.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- specification helper ------------------------------------------------

    def _apply_spec(
        self,
        stmt: Any,
        specification: ISpecification[Any] | None,
    ) -> Any:
        """Compile an ``ISpecification`` to a WHERE clause and apply it."""
        if specification is None:
            return stmt
        spec_data = specification.to_dict()
        if spec_data:
            where_clause = build_sqla_filter(StoredEventModel, spec_data)
            stmt = stmt.where(where_clause)
        return stmt

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
            tenant_id=stored_event.tenant_id,
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
                tenant_id=event.tenant_id,
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
        specification: ISpecification[Any] | None = None,
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
        stmt = self._apply_spec(stmt, specification)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_dataclass(m) for m in models]

    async def get_by_aggregate(
        self,
        aggregate_id: str,
        aggregate_type: str | None = None,
        *,
        specification: ISpecification[Any] | None = None,
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
        stmt = self._apply_spec(stmt, specification)

        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_dataclass(m) for m in models]

    async def get_all(
        self,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> list[StoredEvent]:
        """
        Return every stored event (for projections / catch-up).

        For better performance with large event histories, use
        :meth:`get_events_after` or :meth:`get_all_streaming`.
        """
        stmt = select(StoredEventModel).order_by(StoredEventModel.occurred_at)
        stmt = self._apply_spec(stmt, specification)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_dataclass(m) for m in models]

    async def get_events_after(
        self,
        position: int,
        limit: int = 1000,
        *,
        specification: ISpecification[Any] | None = None,
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
        stmt = self._apply_spec(stmt, specification)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_dataclass(m) for m in models]

    async def get_events_from_position(
        self,
        position: int,
        *,
        limit: int | None = None,
        specification: ISpecification[Any] | None = None,
    ) -> AsyncIterator[StoredEvent]:
        """
        Stream events starting from a given position (exclusive).

        Used by ProjectionWorker to resume after crash.
        """
        batch_size = limit if limit is not None else 1000
        current = position
        while True:
            batch = await self.get_events_after(
                current, batch_size, specification=specification
            )
            for e in batch:
                yield e
            if len(batch) < batch_size:
                break
            last = batch[-1]
            current = (
                last.position if last.position is not None else current + len(batch)
            )

    async def get_latest_position(
        self,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> int | None:
        """
        Get the highest event position in the store.

        Used for catch-up subscription mode.
        """
        from sqlalchemy import func

        stmt = select(func.max(StoredEventModel.position))
        stmt = self._apply_spec(stmt, specification)
        result = await self.session.execute(stmt)
        value = result.scalar()
        return int(value) if value is not None else None

    async def get_all_streaming(
        self,
        batch_size: int = 1000,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> AsyncIterator[list[StoredEvent]]:
        """
        Stream all events in batches for memory-efficient processing.

        Yields batches until all events are consumed. Uses the position
        field from StoredEvent for cursor-based iteration.
        """
        offset = 0
        while True:
            batch = await self.get_events_after(
                offset, batch_size, specification=specification
            )
            if not batch:
                break
            yield batch
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
            tenant_id=model.tenant_id,
        )
