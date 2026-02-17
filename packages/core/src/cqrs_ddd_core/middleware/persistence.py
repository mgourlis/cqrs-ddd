"""EventStorePersistenceMiddleware — auto-persists events to event store."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..ports.middleware import IMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ..ports.event_store import IEventStore


class EventStorePersistenceMiddleware(IMiddleware):
    """Auto-persists events from CommandResponse to IEventStore.

    Runs **after** the handler returns, before the result is propagated
    back up the pipeline.
    """

    def __init__(self, event_store: IEventStore) -> None:
        self._event_store = event_store

    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Execute handler and persist resulting events."""
        result = await next_handler(message)

        # Only persist if the handler returned a response with events
        events = getattr(result, "events", None)
        if events:
            from ..ports.event_store import StoredEvent

            stored: list[StoredEvent] = []
            for event in events:
                stored.append(
                    StoredEvent(
                        event_id=getattr(event, "event_id", ""),
                        event_type=type(event).__name__,
                        aggregate_id=str(getattr(event, "aggregate_id", "")),
                        aggregate_type=getattr(event, "aggregate_type", ""),
                        version=getattr(event, "version", 0),
                        payload=event.model_dump(),
                        metadata=getattr(event, "metadata", {}),
                        occurred_at=getattr(event, "occurred_at", None)
                        or datetime.now(timezone.utc),
                        correlation_id=getattr(event, "correlation_id", None),
                        causation_id=getattr(event, "causation_id", None),
                    )
                )
            await self._event_store.append_batch(stored)

        return result
