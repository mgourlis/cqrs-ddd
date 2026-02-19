"""RabbitMQ connection pooling, reconnect, and health check."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import aio_pika

from ..exceptions import MessagingConnectionError

if TYPE_CHECKING:
    from aio_pika.abc import AbstractChannel, AbstractConnection


class RabbitMQConnectionManager:
    """Manages a single robust connection and channel for RabbitMQ.

    Uses connect_robust for automatic reconnection. Call connect() before use,
    close() on shutdown, and health_check() for probes.
    """

    def __init__(
        self,
        url: str = "amqp://guest:guest@localhost/",
        **connect_kwargs: Any,
    ) -> None:
        """Configure connection URL and optional aio_pika connect kwargs."""
        self._url = url
        self._connect_kwargs = connect_kwargs
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None

    async def connect(self) -> None:
        """Establish connection and channel. Idempotent if already connected."""
        if self._connection is not None and not self._connection.is_closed:
            return
        try:
            self._connection = await aio_pika.connect_robust(
                self._url,
                **self._connect_kwargs,
            )
            self._channel = await self._connection.channel(publisher_confirms=True)
        except (ConnectionError, OSError, ValueError) as e:
            raise MessagingConnectionError(str(e)) from e

    async def close(self) -> None:
        """Close channel and connection."""
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    @property
    def channel(self) -> AbstractChannel:
        """Return the channel; raises if not connected."""
        if self._channel is None:
            raise MessagingConnectionError("Not connected; call connect() first")
        return self._channel

    async def health_check(self) -> bool:
        """Return True if connection and channel are open."""
        if self._connection is None or self._channel is None:
            return False
        return not self._connection.is_closed
