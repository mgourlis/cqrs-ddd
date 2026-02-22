"""ProjectionWorker — process event stream with position tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from cqrs_ddd_core.ports.event_store import StoredEvent

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork


@runtime_checkable
class ProjectionEventHandler(Protocol):
    """Protocol for handlers that process events in a projection."""

    async def handle(
        self,
        event: StoredEvent,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        """Handle a single event, optionally within a UnitOfWork."""
        ...


# Type for handler map: event_type -> handler
HandlerMap = dict[str, ProjectionEventHandler]

# Type for UoW factory: callable returning an async context manager that yields UnitOfWork
AsyncUoWFactory = Any  # Callable[[], AbstractAsyncContextManager[UnitOfWork]]


class ProjectionWorker:
    """
    Consumes events from the event store and updates projections with position
    tracking. Each event is processed inside a UnitOfWork so projection writes
    and position updates commit atomically.

    Supports catch_up mode: when True and no last_position exists, sets position
    to get_latest_position() and saves it (skipping historical replay), then
    streams new events.
    """

    def __init__(
        self,
        event_store: Any,  # IEventStore
        position_store: Any,  # IProjectionPositionStore
        writer: Any,  # IProjectionWriter (optional for handler-only workers)
        handler_map: HandlerMap,
        uow_factory: AsyncUoWFactory,
        *,
        catch_up: bool = False,
    ) -> None:
        self._event_store = event_store
        self._position_store = position_store
        self._writer = writer
        self._handler_map = handler_map
        self._uow_factory = uow_factory
        self._catch_up = catch_up

    async def run(self, projection_name: str) -> None:
        """
        Run the projection: stream events from last saved position (or latest
        if catch_up and never processed), and for each event run the handler
        and save position in the same UoW.
        """
        last_position = await self._position_store.get_position(projection_name)
        start_position: int

        if self._catch_up and last_position is None:
            latest = await self._event_store.get_latest_position()
            if latest is not None:
                async with self._uow_factory() as uow:
                    await self._position_store.save_position(
                        projection_name, latest, uow=uow
                    )
                start_position = latest
            else:
                start_position = 0
        else:
            start_position = last_position if last_position is not None else 0

        async for event in self._event_store.get_events_from_position(start_position):
            position = event.position
            if position is None:
                continue
            async with self._uow_factory() as uow:
                handler = self._handler_map.get(event.event_type)
                if handler is not None:
                    await handler.handle(event, uow=uow)
                await self._position_store.save_position(
                    projection_name, position, uow=uow
                )
