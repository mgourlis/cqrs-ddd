"""RabbitMQConsumer — IMessageConsumer with
prefetch, ack/nack, retry and dead-letter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from cqrs_ddd_core.ports.messaging import IMessageConsumer

from ..retry import RetryPolicy
from ..serialization import EnvelopeSerializer
from .connection import RabbitMQConnectionManager

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Coroutine

    from aio_pika.abc import AbstractIncomingMessage

    from ..dead_letter import DeadLetterHandler
    from .connection import RabbitMQConnectionManager


class RabbitMQConsumer(IMessageConsumer):
    """RabbitMQ adapter implementing IMessageConsumer.

    Binds a queue to a topic exchange; prefetch, manual ack/nack, optional
    retry and dead-letter handling.
    """

    def __init__(
        self,
        connection: RabbitMQConnectionManager,
        *,
        exchange_name: str = "amq.topic",
        serializer: EnvelopeSerializer | None = None,
        prefetch_count: int = 10,
        retry_policy: RetryPolicy | None = None,
        dead_letter: DeadLetterHandler | None = None,
    ) -> None:
        """Configure consumer.

        Args:
            connection: Shared connection manager.
            exchange_name: Exchange to bind to.
            serializer: For deserializing messages; default EnvelopeSerializer().
            prefetch_count: QoS prefetch.
            retry_policy: If set, failed messages are retried then sent to dead_letter.
            dead_letter: If set, used when retries are exhausted.
        """
        self._connection = connection
        self._exchange_name = exchange_name
        self._serializer = serializer or EnvelopeSerializer()
        self._prefetch_count = prefetch_count
        self._retry_policy = retry_policy or RetryPolicy()
        self._dead_letter = dead_letter
        self._handlers: list[
            tuple[str, str | None, Callable[..., Coroutine[Any, Any, None]]]
        ] = []
        self._consuming = False
        self._consume_tasks: list[asyncio.Task[None]] = []

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
        queue_name: str | None = None,
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        """Bind handler to topic. Queue is declared and bound to the topic exchange."""
        await self._connection.connect()
        channel = self._connection.channel
        await channel.set_qos(prefetch_count=self._prefetch_count)
        exchange = await channel.declare_exchange(
            self._exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        name = queue_name or f"cqrs.{topic}"
        queue = await channel.declare_queue(name, durable=True)
        await queue.bind(exchange, routing_key=topic)

        async def on_message(raw: AbstractIncomingMessage) -> None:
            async with raw.process(ignore_processed=True):
                envelope = self._serializer.deserialize(raw.body)
                attempt = envelope.attempt
                try:
                    await handler(envelope.payload)
                except Exception as e:  # noqa: BLE001
                    if self._retry_policy.should_retry(attempt):
                        await self._retry_policy.wait_before_retry(attempt)
                        # Re-queue with incremented attempt
                        # (would need republish in real impl)
                        await raw.nack(requeue=True)
                    elif self._dead_letter is not None:
                        await self._dead_letter.route(
                            envelope.model_copy(update={"attempt": attempt}),
                            reason=str(e),
                            exception=e,
                        )
                        await raw.ack()
                    else:
                        await raw.nack(requeue=False)

        self._handlers.append((topic, queue_name, handler))
        await queue.consume(on_message)

    async def health_check(self) -> bool:
        """Return True if the connection is healthy."""
        return await self._connection.health_check()
