"""PublishingEventHandler — generic handler that publishes events to brokers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.events import DomainEvent
from ..handler import EventHandler

if TYPE_CHECKING:
    from ...ports.messaging import IMessagePublisher

logger = logging.getLogger("cqrs_ddd.publishers")


class PublishingEventHandler(EventHandler[DomainEvent]):
    """Generic handler that publishes events to an external message broker.

    Acts as a bridge between the domain event dispatcher and an IMessagePublisher
    (e.g., OutboxPublisher, RabbitMQ driver, Kafka driver).

    Usage::

        publisher_handler = PublishingEventHandler(publisher=outbox_publisher)
        dispatcher.register(OrderCreated, publisher_handler)
        dispatcher.register(OrderShipped, publisher_handler)
    """

    def __init__(self, publisher: IMessagePublisher) -> None:
        self._publisher = publisher

    async def handle(self, event: DomainEvent) -> None:
        """Publish the event to the configured broker.

        The topic is derived from the event class name.
        """
        topic = type(event).__name__
        try:
            logger.debug(
                "Publishing event %s via %s", topic, type(self._publisher).__name__
            )
            await self._publisher.publish(topic, event)
        except Exception:
            logger.exception("Failed to publish event %s", topic)
            raise
