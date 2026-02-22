"""ProjectionWorker —
IBackgroundWorker that polls IEventStore, dispatches to handlers, checkpoints."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry
from cqrs_ddd_core.ports.background_worker import IBackgroundWorker

from .error_handling import ProjectionErrorPolicy

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
    from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent

    from .ports import ICheckpointStore, IProjectionRegistry


class ProjectionWorker(IBackgroundWorker):
    """Polls IEventStore after checkpoint,
    runs projection handlers, saves checkpoint."""

    def __init__(
        self,
        event_store: IEventStore,
        projection_registry: IProjectionRegistry,
        checkpoint_store: ICheckpointStore,
        *,
        projection_name: str = "default",
        event_registry: EventTypeRegistry | None = None,
        batch_size: int = 100,
        poll_interval_seconds: float = 1.0,
        error_policy: ProjectionErrorPolicy | None = None,
    ) -> None:
        self._event_store = event_store
        self._projection_registry = projection_registry
        self._checkpoint_store = checkpoint_store
        self._projection_name = projection_name
        self._event_registry = event_registry
        self._batch_size = batch_size
        self._poll_interval = poll_interval_seconds
        self._error_policy = error_policy or ProjectionErrorPolicy()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._partition_filter: Callable[[StoredEvent], bool] | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        """Main worker loop using cursor-based event streaming."""
        while self._running:
            try:
                position = await self._get_checkpoint_position()
                batch = await self._event_store.get_events_after(
                    position, self._batch_size
                )

                if not batch:
                    await self._handle_empty_batch()
                    continue

                await self._process_event_batch(position, batch)

            except asyncio.CancelledError:
                logger.debug("Worker cancelled, shutting down")
                break
            except Exception as e:
                logger.error(f"Projection worker error: {e}", exc_info=True)
                await asyncio.sleep(self._poll_interval)

    async def _get_checkpoint_position(self) -> int:
        """Get current checkpoint position, defaulting to 0."""
        position = await self._checkpoint_store.get_position(self._projection_name)
        return position if position is not None else 0

    async def _handle_empty_batch(self) -> None:
        """Handle case when no new events are available."""
        if not self._running:
            return
        await asyncio.sleep(self._poll_interval)

    async def _process_event_batch(
        self, position: int, batch: list[StoredEvent]
    ) -> None:
        """Process a batch of events with retry logic and checkpointing."""
        last_position = position
        for stored in batch:
            if not self._running:
                break

            if not self._should_process_event(stored):
                continue

            # Use actual event position from event store (global sequence number)
            event_position = stored.position
            if event_position is None:
                logger.warning(
                    f"Event {stored.event_id} has no position, skipping"
                )
                continue

            await self._process_event_with_retry(stored, event_position)
            last_position = event_position

        await self._checkpoint_store.save_position(
            self._projection_name, last_position
        )

    def _should_process_event(self, stored: StoredEvent) -> bool:
        """Check if event should be processed based on partition filter."""
        if self._partition_filter is None:
            return True
        return self._partition_filter(stored)

    async def _process_event_with_retry(
        self, stored: StoredEvent, event_position: int
    ) -> None:
        """Process a single event with retry logic for transient failures."""
        registry = get_hook_registry()
        await registry.execute_all(
            f"projection.process.{self._projection_name}",
            {
                "projection.name": self._projection_name,
                "projection.position": event_position,
                "event.id": str(stored.event_id),
                "event.type": stored.event_type,
                "correlation_id": get_correlation_id()
                or getattr(stored, "correlation_id", None),
            },
            lambda: self._process_event_with_retry_internal(stored, event_position),
        )

    async def _process_event_with_retry_internal(
        self, stored: StoredEvent, event_position: int
    ) -> None:
        """Process a single event with retry logic for transient failures."""
        retry_count = 0
        max_retries = self._error_policy.max_retries

        while retry_count <= max_retries:
            try:
                domain_event = self._hydrate(stored)
                if domain_event is None:
                    self._log_hydration_failure(stored)
                    return

                await self._dispatch(domain_event, stored, event_position, retry_count)
                return

            except Exception as e:
                if retry_count == max_retries:
                    logger.error(
                        f"Failed to process event {stored.event_id} "
                        f"after {retry_count} retries: {e}",
                        exc_info=True,
                    )
                    return
                retry_count += 1

    def _log_hydration_failure(self, stored: StoredEvent) -> None:
        """Log appropriate warning based on why hydration failed."""
        if self._event_registry is None:
            logger.warning(f"EventRegistry not set, skipping event {stored.event_id}")
        else:
            logger.warning(
                f"Failed to hydrate event {stored.event_type}:{stored.event_id}"
            )

    def _hydrate(self, stored: StoredEvent) -> Any:
        if self._event_registry is None:
            return None
        return self._event_registry.hydrate(stored.event_type, dict(stored.payload))

    async def _dispatch(
        self, event: Any, stored: StoredEvent, _event_position: int, retry_count: int
    ) -> None:
        """Dispatch event to all registered handlers."""
        handlers = self._projection_registry.get_handlers(stored.event_type)
        for handler in handlers:
            try:
                await handler.handle(event)
            except Exception as e:  # noqa: BLE001
                await self._error_policy.handle_failure(event, e, retry_count)
