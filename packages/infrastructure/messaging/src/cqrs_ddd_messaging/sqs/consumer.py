"""SQSConsumer — IMessageConsumer with long-polling and visibility timeout."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.ports.messaging import IMessageConsumer

from ..retry import RetryPolicy
from ..serialization import EnvelopeSerializer

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from ..dead_letter import DeadLetterHandler
    from .connection import SQSConnectionManager


class SQSConsumer(IMessageConsumer):
    """SQS adapter implementing IMessageConsumer.

    Long-polling via WaitTimeSeconds; extend visibility timeout for long handlers.
    """

    def __init__(
        self,
        connection: SQSConnectionManager,
        *,
        serializer: EnvelopeSerializer | None = None,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 30,
        retry_policy: RetryPolicy | None = None,
        dead_letter: DeadLetterHandler | None = None,
    ) -> None:
        """Configure consumer.

        Args:
            connection: Shared connection manager.
            serializer: For deserializing messages; default EnvelopeSerializer().
            wait_time_seconds: Long-poll wait.
            visibility_timeout: Visibility timeout for received messages.
            retry_policy: If set, failed messages are retried then sent to dead_letter.
            dead_letter: If set, used when retries are exhausted.
        """
        self._connection = connection
        self._serializer = serializer or EnvelopeSerializer()
        self._wait_time_seconds = wait_time_seconds
        self._visibility_timeout = visibility_timeout
        self._retry_policy = retry_policy or RetryPolicy()
        self._dead_letter = dead_letter
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def subscribe(
        self,
        topic: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
        queue_name: str | None = None,
        **kwargs: Any,  # noqa: ARG002
    ) -> None:
        """Register handler for the topic. queue_name/topic
        is used to resolve queue URL."""
        queue_key = queue_name or topic
        self._handlers[queue_key] = handler

    async def _process_message(
        self,
        client: Any,
        queue_url: str,
        msg: dict[str, Any],
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> None:
        """Handle one SQS message: invoke handler, then delete or retry/DLQ."""
        body = msg.get("Body", "")
        receipt = msg["ReceiptHandle"]
        raw = body.encode("utf-8") if isinstance(body, str) else body
        envelope = self._serializer.deserialize(raw)
        attempt = envelope.attempt
        try:
            await handler(envelope.payload)
            await client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt,
            )
        except Exception as e:  # noqa: BLE001
            if self._retry_policy.should_retry(attempt):
                await self._retry_policy.wait_before_retry(attempt)
                await client.change_message_visibility(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt,
                    VisibilityTimeout=0,
                )
            elif self._dead_letter is not None:
                await self._dead_letter.route(
                    envelope.model_copy(update={"attempt": attempt}),
                    reason=str(e),
                    exception=e,
                )
                await client.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt,
                )
            else:
                await client.change_message_visibility(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt,
                    VisibilityTimeout=0,
                )

    async def run(self) -> None:
        """Poll SQS and dispatch to handlers. Call after subscribe()."""
        self._running = True
        client = await self._connection.get_client()
        while self._running:
            for queue_key, handler in list(self._handlers.items()):
                queue_url = await self._connection.get_queue_url(queue_key)
                try:
                    out = await client.receive_message(
                        QueueUrl=queue_url,
                        MaxNumberOfMessages=10,
                        WaitTimeSeconds=self._wait_time_seconds,
                        VisibilityTimeout=self._visibility_timeout,
                    )
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(1)
                    continue
                for msg in out.get("Messages", []):
                    if not self._running:
                        break
                    await self._process_message(client, queue_url, msg, handler)

    async def stop(self) -> None:
        """Stop the consumer loop."""
        self._running = False

    async def health_check(self) -> bool:
        """Return True if SQS is reachable."""
        return await self._connection.health_check()
