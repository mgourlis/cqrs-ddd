"""KafkaPublisher — IMessagePublisher with partition key routing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiokafka import AIOKafkaProducer

from cqrs_ddd_core.ports.messaging import IMessagePublisher

from ..envelope import MessageEnvelope
from ..exceptions import MessagingSerializationError
from ..serialization import EnvelopeSerializer
from .connection import KafkaConnectionManager

if TYPE_CHECKING:
    from .connection import KafkaConnectionManager


def _message_to_envelope(message: Any, _topic: str, **kwargs: Any) -> MessageEnvelope:
    """Build MessageEnvelope from message and kwargs."""
    if isinstance(message, MessageEnvelope):
        return message
    payload: dict[str, object]
    event_type: str
    if hasattr(message, "model_dump"):
        payload = message.model_dump()
        event_type = getattr(message, "event_type", message.__class__.__name__)
    elif isinstance(message, dict):
        payload = message
        event_type = str(message.get("event_type", kwargs.get("event_type", "unknown")))
    else:
        payload = {"value": message}
        event_type = str(kwargs.get("event_type", "unknown"))
    return MessageEnvelope(
        event_type=event_type,
        payload=payload,
        correlation_id=kwargs.get("correlation_id"),
        causation_id=kwargs.get("causation_id"),
        headers=kwargs.get("headers") or {},
    )


class KafkaPublisher(IMessagePublisher):
    """Kafka adapter implementing IMessagePublisher.

    Uses topic as Kafka topic name; partition key defaults to aggregate_id for ordering.
    """

    def __init__(
        self,
        connection: KafkaConnectionManager,
        *,
        serializer: EnvelopeSerializer | None = None,
    ) -> None:
        """Configure publisher.

        Args:
            connection: Shared connection config.
            serializer: Used to serialize envelopes; default EnvelopeSerializer().
        """
        self._connection = connection
        self._serializer = serializer or EnvelopeSerializer()
        self._producer: AIOKafkaProducer | None = None

    async def _get_producer(self) -> AIOKafkaProducer:
        """Create or return existing producer."""
        if self._producer is not None:
            return self._producer
        self._producer = AIOKafkaProducer(**self._connection.producer_config())
        await self._producer.start()
        return self._producer

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        """Publish message to Kafka topic.
        Partition key = kwargs.get('aggregate_id') or message.aggregate_id."""
        producer = await self._get_producer()
        envelope = _message_to_envelope(message, topic, **kwargs)
        try:
            body = self._serializer.serialize(envelope)
        except Exception as e:
            raise MessagingSerializationError(str(e)) from e
        key = None
        if hasattr(message, "aggregate_id") and message.aggregate_id:
            key = message.aggregate_id.encode("utf-8")
        elif isinstance(message, MessageEnvelope) and message.payload:
            aid = message.payload.get("aggregate_id")
            if aid is not None:
                key = str(aid).encode("utf-8")
        key = key or kwargs.get("partition_key")
        if isinstance(key, str):
            key = key.encode("utf-8")
        await producer.send_and_wait(topic, value=body, key=key)

    async def close(self) -> None:
        """Stop the producer."""
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def health_check(self) -> bool:
        """Return True if the cluster is reachable."""
        return await self._connection.health_check()
