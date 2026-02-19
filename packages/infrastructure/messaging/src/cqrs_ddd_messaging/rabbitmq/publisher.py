"""RabbitMQPublisher — IMessagePublisher with topic exchange and publisher confirms."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import aio_pika

from cqrs_ddd_core.ports.messaging import IMessagePublisher

from ..envelope import MessageEnvelope
from ..exceptions import MessagingSerializationError
from ..serialization import EnvelopeSerializer

if TYPE_CHECKING:
    from aio_pika.abc import AbstractExchange

    from .connection import RabbitMQConnectionManager


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


class RabbitMQPublisher(IMessagePublisher):
    """RabbitMQ adapter implementing IMessagePublisher.

    Uses a topic exchange; topic is the routing key. Supports publisher confirms.
    """

    def __init__(
        self,
        connection: RabbitMQConnectionManager,
        *,
        exchange_name: str = "amq.topic",
        serializer: EnvelopeSerializer | None = None,
        confirm_delivery: bool = True,
    ) -> None:
        """Configure publisher.

        Args:
            connection: Shared connection manager.
            exchange_name: Exchange to publish to (default amq.topic).
            serializer: Used to serialize envelopes; default EnvelopeSerializer().
            confirm_delivery: Enable publisher confirms when True.
        """
        self._connection = connection
        self._exchange_name = exchange_name
        self._serializer = serializer or EnvelopeSerializer()
        self._confirm_delivery = confirm_delivery
        self._exchange: AbstractExchange | None = None

    async def _ensure_exchange(self) -> AbstractExchange:
        """Declare topic exchange (confirms enabled on the channel in connection)."""
        if self._exchange is not None:
            return self._exchange
        channel = self._connection.channel
        self._exchange = await channel.declare_exchange(
            self._exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        return self._exchange

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        """Publish message to topic (routing_key).
        Message is wrapped in MessageEnvelope if needed."""
        await self._connection.connect()
        exchange = await self._ensure_exchange()
        envelope = _message_to_envelope(message, topic, **kwargs)
        try:
            body = self._serializer.serialize(envelope)
        except Exception as e:
            raise MessagingSerializationError(str(e)) from e
        await exchange.publish(
            aio_pika.Message(
                body=body,
                content_type="application/json",
                headers={
                    "event_type": envelope.event_type,
                    **{k: (v or "") for k, v in envelope.headers.items()},
                },
            ),
            routing_key=topic,
        )

    async def health_check(self) -> bool:
        """Return True if the connection is healthy."""
        return await self._connection.health_check()
