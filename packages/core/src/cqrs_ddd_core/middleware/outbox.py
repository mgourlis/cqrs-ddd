"""OutboxMiddleware — automatically publishes domain events to the outbox."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..cqrs.response import CommandResponse
from ..ports.middleware import IMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ..ports.messaging import IMessagePublisher

logger = logging.getLogger("cqrs_ddd.middleware")


class OutboxMiddleware(IMiddleware):
    """
    Middleware that automatically publishes domain events to an outbox.

    For every command that produces events, this middleware will:
    1. Execute the command handler
    2. Collect domain events from the response
    3. Publish each event to the configured outbox (e.g., BufferedOutbox)

    The outbox handles transactional writes and background publishing.

    Usage::

        buffered_outbox = BufferedOutbox(storage, broker)

        middleware_pipeline = [
            OutboxMiddleware(outbox=buffered_outbox),
            # ... other middleware
        ]
    """

    def __init__(self, outbox: IMessagePublisher) -> None:
        self._outbox = outbox

    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Execute the handler and publish resulting events."""
        result = await next_handler(message)

        # If this was a command, publish its events
        if isinstance(result, CommandResponse):
            for event in result.events:
                topic = type(event).__name__
                logger.debug("Publishing event %s to outbox", topic)
                
                # Extract tracing IDs from enriched DomainEvent
                # (Mediator has already called enrich_event_metadata)
                tracing_kwargs = {}
                if hasattr(event, "correlation_id") and event.correlation_id:
                    tracing_kwargs["correlation_id"] = event.correlation_id
                if hasattr(event, "causation_id") and event.causation_id:
                    tracing_kwargs["causation_id"] = event.causation_id
                
                await self._outbox.publish(topic, event, **tracing_kwargs)

        return result
