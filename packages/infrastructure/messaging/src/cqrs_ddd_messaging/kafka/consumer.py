"""KafkaConsumer — IMessageConsumer with consumer groups and manual offset commit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiokafka import AIOKafkaConsumer

from cqrs_ddd_core.ports.messaging import IMessageConsumer

from ..retry import RetryPolicy
from ..serialization import EnvelopeSerializer

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Coroutine

    from ..dead_letter import DeadLetterHandler
    from .connection import KafkaConnectionManager


class KafkaConsumer(IMessageConsumer):
    """Kafka adapter implementing IMessageConsumer.

    Uses consumer groups; topic is the Kafka topic.
    Manual offset commit (commit after handler).
    """

    def __init__(
        self,
        connection: KafkaConnectionManager,
        *,
        group_id: str = "cqrs-ddd",
        serializer: EnvelopeSerializer | None = None,
        retry_policy: RetryPolicy | None = None,
        dead_letter: DeadLetterHandler | None = None,
    ) -> None:
        """Configure consumer.

        Args:
            connection: Shared connection config.
            group_id: Kafka consumer group id.
            serializer: For deserializing messages; default EnvelopeSerializer().
            retry_policy: If set, failed messages are retried then sent to dead_letter.
            dead_letter: If set, used when retries are exhausted.
        """
        self._connection = connection
        self._group_id = group_id
        self._serializer = serializer or EnvelopeSerializer()
        self._retry_policy = retry_policy or RetryPolicy()
        self._dead_letter = dead_letter
        self._consumer: AIOKafkaConsumer | None = None
        self._topic_handlers: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def _handle_message(
        self, consumer: AIOKafkaConsumer, msg: Any, handler: Any
    ) -> None:
        """Process a single message: invoke handler, commit or retry/DLQ."""
        envelope = self._serializer.deserialize(msg.value)
        attempt = envelope.attempt
        try:
            await handler(envelope.payload)
            await consumer.commit()
        except Exception as e:  # noqa: BLE001
            if self._retry_policy.should_retry(attempt):
                await self._retry_policy.wait_before_retry(attempt)
                await consumer.commit()
            elif self._dead_letter is not None:
                await self._dead_letter.route(
                    envelope.model_copy(update={"attempt": attempt}),
                    reason=str(e),
                    exception=e,
                )
                await consumer.commit()
            else:
                await consumer.commit()

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
        queue_name: str | None = None,
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        """Register handler for the topic. queue_name overrides group_id if provided."""
        group = queue_name or self._group_id
        self._topic_handlers[topic] = handler
        topics = list(self._topic_handlers)
        if self._consumer is None:
            self._consumer = AIOKafkaConsumer(
                *topics,
                group_id=group,
                enable_auto_commit=False,
                **self._connection.consumer_config(),
            )
            await self._consumer.start()
        else:
            self._consumer.subscribe(topics)

    async def run(self) -> None:
        """Process messages until stopped. Call after subscribe()."""
        consumer = self._consumer
        if consumer is None:
            return
        self._running = True
        try:
            async for msg in consumer:
                if not self._running:
                    break
                handler = self._topic_handlers.get(msg.topic)
                if handler is not None:
                    await self._handle_message(consumer, msg, handler)
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the consumer loop."""
        self._running = False
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def health_check(self) -> bool:
        """Return True if the cluster is reachable."""
        return await self._connection.health_check()
