"""SQSPublisher — IMessagePublisher with FIFO dedup and long-polling support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.messaging import IMessagePublisher

from ..envelope import MessageEnvelope
from ..exceptions import MessagingSerializationError
from ..serialization import EnvelopeSerializer

if TYPE_CHECKING:
    from .connection import SQSConnectionManager


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


class SQSPublisher(IMessagePublisher):
    """SQS adapter implementing IMessagePublisher.

    Topic is used as queue name (or queue_url via kwargs). FIFO queues use
    message_id as deduplication id when available.
    """

    def __init__(
        self,
        connection: SQSConnectionManager,
        *,
        serializer: EnvelopeSerializer | None = None,
    ) -> None:
        """Configure publisher.

        Args:
            connection: Shared connection manager.
            serializer: Used to serialize envelopes; default EnvelopeSerializer().
        """
        self._connection = connection
        self._serializer = serializer or EnvelopeSerializer()

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        """Publish message to the queue named by topic (or queue_url in kwargs)."""
        queue_url = kwargs.get("queue_url")
        if queue_url is None:
            queue_url = await self._connection.get_queue_url(topic)
        envelope = _message_to_envelope(message, topic, **kwargs)
        try:
            body = self._serializer.serialize(envelope)
        except Exception as e:
            raise MessagingSerializationError(str(e)) from e
        client = await self._connection.get_client()
        send_kwargs: dict[str, Any] = {
            "QueueUrl": queue_url,
            "MessageBody": body.decode("utf-8"),
        }
        if queue_url.endswith(".fifo"):
            send_kwargs["MessageDeduplicationId"] = envelope.message_id
            send_kwargs["MessageGroupId"] = str(
                envelope.payload.get("aggregate_id") or "default"
            )
        await client.send_message(**send_kwargs)

    async def health_check(self) -> bool:
        """Return True if SQS is reachable."""
        return await self._connection.health_check()
