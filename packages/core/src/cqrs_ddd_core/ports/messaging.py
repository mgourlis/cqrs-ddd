from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


@runtime_checkable
class IMessagePublisher(Protocol):
    """
    Port for publishing messages to a transport (RabbitMQ, Kafka, SQS, …).

    Infrastructure packages provide concrete adapters.
    """

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        """
        Publish *message* to *topic*.

        Args:
            topic: Routing key, topic name, or exchange.
            message: Payload — may be a domain event, dict, or bytes.
            **kwargs: Transport-specific metadata
                (``correlation_id``, ``causation_id``, headers, …).
        """
        ...


@runtime_checkable
class IMessageConsumer(Protocol):
    """
    Port for subscribing to messages from a transport.

    Infrastructure packages provide concrete adapters.
    """

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
        queue_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Subscribe *handler* to *topic*.

        Args:
            topic: Routing key or queue to bind.
            handler: Async callable invoked for each message.
            queue_name: Optional consumer-group / queue name.
            **kwargs: Transport-specific options.
        """
        ...
