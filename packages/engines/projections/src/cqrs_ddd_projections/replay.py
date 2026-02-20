"""ReplayEngine — rebuild projections from full event history."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .error_handling import ProjectionErrorPolicy

if TYPE_CHECKING:
    from collections.abc import Callable

    from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
    from cqrs_ddd_core.ports.event_store import IEventStore

    from .ports import ICheckpointStore, IProjectionRegistry

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Rebuilds a projection from event store: reset checkpoint,
    iterate all events, run handlers."""

    def __init__(
        self,
        event_store: IEventStore,
        projection_registry: IProjectionRegistry,
        checkpoint_store: ICheckpointStore,
        *,
        event_registry: EventTypeRegistry | None = None,
        batch_size: int = 500,
        error_policy: ProjectionErrorPolicy | None = None,
    ) -> None:
        self._event_store = event_store
        self._projection_registry = projection_registry
        self._checkpoint_store = checkpoint_store
        self._event_registry = event_registry
        self._batch_size = batch_size
        self._error_policy = error_policy or ProjectionErrorPolicy(policy="skip")

    async def replay(
        self,
        projection_name: str,
        *,
        from_position: int = 0,
        on_drop: Callable[[], Any] | None = None,
        progress_callback: Callable[[int, int, float], Any] | None = None,
    ) -> None:
        """Replay projection from position using streaming API.
        Optionally call on_drop() to clear read model first."""
        await self._execute_on_drop(on_drop)
        await self._checkpoint_store.save_position(projection_name, from_position)

        position = from_position
        processed = 0

        async for batch in self._event_store.get_all_streaming(
            batch_size=self._batch_size
        ):
            for stored in batch:
                domain_event = self._hydrate_event(stored)
                if domain_event is not None:
                    await self._dispatch_to_handlers(stored, domain_event)
                processed += 1
                await self._report_progress(progress_callback, processed)
            position += len(batch)
            await self._checkpoint_store.save_position(projection_name, position)

    async def _execute_on_drop(self, on_drop: Callable[[], Any] | None) -> None:
        """Execute on_drop callback if provided, handling both sync and async."""
        if not on_drop:
            return
        result = on_drop()
        if hasattr(result, "__await__"):
            await result

    def _hydrate_event(self, stored: Any) -> Any:
        """Hydrate domain event from stored event using event registry."""
        if not self._event_registry:
            return None
        return self._event_registry.hydrate(stored.event_type, dict(stored.payload))

    async def _dispatch_to_handlers(self, stored: Any, domain_event: Any) -> None:
        """Dispatch event to all registered handlers with error handling."""
        handlers = self._projection_registry.get_handlers(stored.event_type)
        for handler in handlers:
            try:
                await handler.handle(domain_event)
            except Exception as e:
                logger.error(
                    f"Handler failed during replay for event {stored.event_id}: {e}",
                    exc_info=True,
                )
                await self._error_policy.handle_failure(domain_event, e, 1)

    async def _report_progress(
        self,
        progress_callback: Callable[[int, int, float], Any] | None,
        processed: int,
    ) -> None:
        """Report progress to callback if provided, handling both sync and async."""
        if not progress_callback:
            return
        result = progress_callback(processed, -1, 0.0)
        if hasattr(result, "__await__"):
            await result
