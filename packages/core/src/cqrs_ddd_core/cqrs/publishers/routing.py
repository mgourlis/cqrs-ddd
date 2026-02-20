"""TopicRoutingPublisher — route events to different publishers based on metadata."""

from __future__ import annotations

import logging
from typing import Any

from ...correlation import get_correlation_id
from ...instrumentation import get_hook_registry
from ...ports.messaging import IMessagePublisher

logger = logging.getLogger("cqrs_ddd.publishers")


class TopicRoutingPublisher(IMessagePublisher):
    """Routes message publications based on topic/event type.

    Resolution order:
    1. Check if event class has a ``__route_to__`` attribute (via ``@route_to``).
    2. Check if topic/event name is in explicit ``routes`` dict.
    3. Fall back to ``default`` publisher.

    Usage::

        router = TopicRoutingPublisher(
            routes={
                "UserCreated": outbox_publisher,
            },
            destinations={
                "slow": background_jobs_publisher,
            },
            default=outbox_publisher,
        )
    """

    def __init__(
        self,
        routes: dict[str, IMessagePublisher] | None = None,
        destinations: dict[str, IMessagePublisher] | None = None,
        default: IMessagePublisher | None = None,
    ) -> None:
        self._routes = routes or {}
        self._destinations = destinations or {}
        self._default = default

    def register_route(self, topic: str, publisher: IMessagePublisher) -> None:
        """Register a specific publisher for a topic (event class name)."""
        self._routes[topic] = publisher
        logger.debug("Registered route: %s -> %s", topic, type(publisher).__name__)

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        """Route the message to the appropriate publisher."""
        registry = get_hook_registry()
        attributes = {
            "topic": topic,
            "message_type": type(message),
            "correlation_id": kwargs.get("correlation_id") or get_correlation_id(),
        }

        async def _publish() -> None:
            publisher: IMessagePublisher | None = None

            # 1. Check for destination key on the message/event class
            # (Usually set via @route_to decorator)
            dest_key = getattr(message, "__route_to__", None)
            if not dest_key and hasattr(message, "__class__"):
                dest_key = getattr(message.__class__, "__route_to__", None)

            if dest_key:
                publisher = self._destinations.get(dest_key)
                if publisher:
                    logger.debug(
                        "Resolved auto-route: %s -> %s -> %s",
                        topic,
                        dest_key,
                        type(publisher).__name__,
                    )

            # 2. Check explicit topic route (overrides auto-route)
            if topic in self._routes:
                publisher = self._routes[topic]

            # 3. Fall back to default
            if not publisher:
                publisher = self._default

            if not publisher:
                msg = (
                    f"No publisher configured for topic '{topic}' "
                    "and no default provided."
                )
                logger.error(msg)
                from ...primitives.exceptions import PublisherNotFoundError

                raise PublisherNotFoundError(msg)

            await publisher.publish(topic, message, **kwargs)

        await registry.execute_all(
            f"publisher.publish.{topic}",
            attributes,
            _publish,
        )
