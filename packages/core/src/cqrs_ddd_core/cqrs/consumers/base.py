"""BaseEventConsumer — subscribe to brokers, hydrate, and dispatch events."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...correlation import get_correlation_id
from ...domain.event_registry import EventTypeRegistry
from ...instrumentation import get_hook_registry

if TYPE_CHECKING:
    from collections.abc import Callable

    from ...ports.event_dispatcher import IEventDispatcher
    from ...ports.messaging import IMessageConsumer
    from ..registry import HandlerRegistry

logger = logging.getLogger("cqrs_ddd.consumers")


class BaseEventConsumer:
    """Base implementation of an event consumer (message broker subscriber).

    Subscribes to one or more topics on a message broker.
    When a message is received:
    1. Extracts the ``event_type`` from the payload
    2. Hydrates the payload using ``EventTypeRegistry``
    3. Dispatches the hydrated event using ``IEventDispatcher``

    Usage::

        registry = EventTypeRegistry()
        registry.register("OrderCreated", OrderCreated)

        consumer = BaseEventConsumer(
            broker=kafka_consumer,
            dispatcher=event_dispatcher,
            registry=registry,
            topics=["order-events", "user-events"]
        )
        await consumer.start()
    """

    def __init__(
        self,
        broker: IMessageConsumer,
        topics: list[str],
        *,
        dispatcher: IEventDispatcher[Any] | None = None,
        registry: EventTypeRegistry | None = None,
        handler_registry: HandlerRegistry | None = None,
        handler_factory: Callable[[type[Any]], Any] | None = None,
        queue_name: str | None = None,
        exchange_name: str | None = None,
    ) -> None:
        """Initialize the event consumer.

        Args:
            broker: The message consumer (IMessageConsumer).
            topics: List of topics to subscribe to.
            dispatcher: Optional event dispatcher. If not provided,
                a default one is created.
            registry: Optional event type registry for hydration.
            handler_registry: Optional handler registry for auto-wiring.
            handler_factory: Optional factory for handler instances.
            queue_name: Optional explicit queue name.
            exchange_name: Optional explicit exchange name.
        """
        self._broker = broker
        self._topics = topics
        # Import EventDispatcher here to avoid circular dependencies
        from ..event_dispatcher import EventDispatcher

        self._dispatcher = dispatcher or EventDispatcher()
        self._registry = registry or EventTypeRegistry()
        self._queue_name = queue_name
        self._exchange_name = exchange_name
        self._handler_factory = handler_factory or (lambda cls: cls())
        self._running = False

        if handler_registry:
            self.autoload_event_handlers(handler_registry)

    def autoload_event_handlers(self, registry: HandlerRegistry) -> None:
        """Instantiate and bind asynchronous event handlers from the registry.

        Uses the configured ``handler_factory`` to create instances of the
        handler classes registered in the registry as asynchronous.
        """
        handlers_map = registry.get_all_asynchronous_event_handlers()

        for event_type, handlers in handlers_map.items():
            for handler_cls in handlers:
                handler_instance = self._handler_factory(handler_cls)
                self._dispatcher.register(event_type, handler_instance)

    async def start(self) -> None:
        """Start subscribing to topics and listening for messages."""
        if self._running:
            return

        self._running = True
        logger.info("Starting EventConsumer for topics: %s", self._topics)

        for topic in self._topics:
            kwargs: dict[str, Any] = {}
            if self._exchange_name:
                kwargs["exchange_name"] = self._exchange_name

            await self._broker.subscribe(
                topic=topic,
                handler=self._handle_message,
                queue_name=self._queue_name,
                **kwargs,
            )

        logger.info("EventConsumer started and subscribed")

    async def stop(self) -> None:
        """Stop listening to messages."""
        self._running = False
        logger.info("EventConsumer stopped")

    async def _handle_message(self, payload: Any) -> None:
        """Internal handler that processes broker messages.

        Expects payload to be a dict with 'event_type' key.
        """
        if not isinstance(payload, dict):
            logger.warning(
                "Consumer received non-dict payload: %s",
                type(payload).__name__,
            )
            return

        event_type = payload.get("event_type")
        if not event_type:
            logger.warning("Consumer received payload without 'event_type'")
            return

        try:
            # Hydrate event
            event = self._registry.hydrate(event_type, payload)

            if not event:
                logger.warning(
                    "Failed to hydrate event of type '%s'. Is it registered?",
                    event_type,
                )
                return

            # Dispatch locally
            logger.debug("Consumer hydrated and dispatching %s", event_type)
            registry = get_hook_registry()
            attributes = {
                "event.type": event_type,
                "message_type": type(event),
                "correlation_id": get_correlation_id()
                or getattr(event, "correlation_id", None),
            }
            await registry.execute_all(
                f"consumer.consume.{event_type}",
                attributes,
                lambda: self._dispatcher.dispatch([event]),
            )

        except Exception:
            logger.exception(
                "Error in EventConsumer while processing %s",
                event_type,
            )
