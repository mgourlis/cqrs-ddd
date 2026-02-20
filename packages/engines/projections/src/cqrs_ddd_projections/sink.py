"""EventSinkRunner —
IBackgroundWorker that consumes from IMessageConsumer, dispatches, checkpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry
from cqrs_ddd_core.ports.background_worker import IBackgroundWorker

from .error_handling import ProjectionErrorPolicy

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
    from cqrs_ddd_core.ports.messaging import IMessageConsumer

    from .ports import ICheckpointStore, IProjectionRegistry


class EventSinkRunner(IBackgroundWorker):
    """Consumes from IMessageConsumer (e.g. RabbitMQ/Kafka),
    runs handlers, checkpoints by broker offset."""

    def __init__(
        self,
        consumer: IMessageConsumer,
        projection_registry: IProjectionRegistry,
        checkpoint_store: ICheckpointStore,
        *,
        projection_name: str = "sink",
        topic: str = "events",
        queue_name: str | None = None,
        event_registry: EventTypeRegistry | None = None,
        error_policy: ProjectionErrorPolicy | None = None,
    ) -> None:
        self._consumer = consumer
        self._projection_registry = projection_registry
        self._checkpoint_store = checkpoint_store
        self._projection_name = projection_name
        self._topic = topic
        self._queue_name = queue_name
        self._event_registry = event_registry
        self._error_policy = error_policy or ProjectionErrorPolicy()
        self._offset: int = 0
        self._running: bool = False

    async def start(self) -> None:
        """Subscribe to topic; handler will dispatch and update checkpoint."""
        # Restore offset from checkpoint
        self._offset = (
            await self._checkpoint_store.get_position(self._projection_name) or 0
        )
        self._running = True

        async def on_message(payload: Any, **kwargs: Any) -> None:
            event_type = kwargs.get("event_type") or (
                payload.get("event_type") if isinstance(payload, dict) else None
            )
            if not event_type:
                logger.warning(f"Message missing event_type: {payload}")
                return

            # Hydrate domain event if registry is available
            domain_event = None
            if self._event_registry and isinstance(payload, dict):
                domain_event = self._event_registry.hydrate(event_type, payload)
            if domain_event is None:
                logger.warning(f"Failed to hydrate event {event_type}")
                return

            handlers = self._projection_registry.get_handlers(event_type)
            registry = get_hook_registry()
            for handler in handlers:
                try:

                    async def _handle_event(h: Any = handler) -> None:
                        await h.handle(domain_event)

                    await registry.execute_all(
                        f"projection_sink.write.{self._projection_name}",
                        {
                            "projection.name": self._projection_name,
                            "event.type": event_type,
                            "handler.type": type(handler).__name__,
                            "correlation_id": get_correlation_id()
                            or getattr(domain_event, "correlation_id", None),
                        },
                        _handle_event,
                    )
                except Exception as e:  # noqa: BLE001
                    await self._error_policy.handle_failure(domain_event, e, 1)
            self._offset += 1
            await self._checkpoint_store.save_position(
                self._projection_name, self._offset
            )

        await self._consumer.subscribe(
            self._topic,
            on_message,
            queue_name=self._queue_name,
        )

    async def stop(self) -> None:
        """Gracefully stop consumer and save final checkpoint."""
        self._running = False
        # Note: Actual unsubscribe is transport-specific.
        # IMessageConsumer protocol should have unsubscribe() method,
        # or this can be extended per transport implementation.
        # For now, we save final checkpoint and let the connection close naturally.
        if self._offset is not None:
            await self._checkpoint_store.save_position(
                self._projection_name, self._offset
            )
