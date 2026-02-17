"""OutboxService — core logic for processing the transactional outbox."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...primitives.exceptions import ConcurrencyError
from ...primitives.locking import ResourceIdentifier

if TYPE_CHECKING:
    from ...ports.locking import ILockStrategy
    from ...ports.messaging import IMessagePublisher
    from ...ports.outbox import IOutboxStorage, OutboxMessage

logger = logging.getLogger("cqrs_ddd.outbox")


class OutboxService:
    """
    Processes pending outbox messages in batches with lock-based claiming.

    Lifecycle per batch:
    1. Fetch pending messages from ``IOutboxStorage``.
    2. **Claim batch via locks** (prevents duplicate processing by other workers).
    3. Publish each via ``IMessagePublisher``.
    4. Mark successfully published messages; record failures for retry.

    Lock strategy prevents race conditions when multiple workers process
    the same outbox concurrently.
    """

    def __init__(
        self,
        storage: IOutboxStorage,
        publisher: IMessagePublisher,
        lock_strategy: ILockStrategy,
        *,
        max_retries: int = 5,
    ) -> None:
        self.storage = storage
        self.publisher = publisher
        self.lock_strategy = lock_strategy
        self.max_retries = max_retries

    async def process_batch(self, batch_size: int = 50) -> int:
        """
        Process up to *batch_size* pending messages using two-phase locking.

        Phase 1: Claim messages individually (keep locks held)
        Phase 2: Process batch with held locks, then release

        This prevents race conditions while maintaining batch optimization.

        Returns the number of messages successfully published.
        """
        messages: list[OutboxMessage] = await self.storage.get_pending(batch_size)
        if not messages:
            return 0

        # Phase 1: Claim messages individually and HOLD locks
        acquired: list[tuple[OutboxMessage, ResourceIdentifier, str]] = []

        for msg in messages:
            resource = ResourceIdentifier("OutboxMessage", msg.message_id)
            try:
                token = await self.lock_strategy.acquire(
                    resource,
                    timeout=0.01,  # Fail fast if locked
                    ttl=30.0,  # Hold during processing
                )
                acquired.append((msg, resource, token))
            except ConcurrencyError:
                # Another worker has this message - skip it
                continue

        if not acquired:
            logger.debug("No messages could be claimed (all locked by other workers)")
            return 0

        logger.debug(
            "Claimed %d/%d messages for processing",
            len(acquired),
            len(messages),
        )

        # Phase 2: Process batch with held locks
        try:
            published_ids: list[str] = []
            for msg, _, _ in acquired:
                try:
                    await self.publisher.publish(
                        topic=msg.event_type,
                        message=msg.payload,
                        correlation_id=msg.metadata.get("correlation_id"),
                    )
                    published_ids.append(msg.message_id)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Failed to publish outbox message %s: %s",
                        msg.message_id,
                        exc,
                    )
                    await self.storage.mark_failed(msg.message_id, str(exc))

            # Batch DB update!
            if published_ids:
                await self.storage.mark_published(published_ids)

            return len(published_ids)

        finally:
            # Always release all locks (even if processing failed)
            for _, resource, token in acquired:
                try:
                    await self.lock_strategy.release(resource, token)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to release lock for %s: %s (will auto-expire)",
                        resource,
                        exc,
                    )

    async def retry_failed(self, batch_size: int = 50) -> int:
        """
        Re-attempt publishing for failed messages that haven't
        exceeded ``max_retries``.

        Uses two-phase locking to claim messages gracefully.

        Returns the number of messages successfully retried.
        """
        pending = await self.storage.get_pending(batch_size)
        # Filter to only previously-failed messages eligible for retry.
        retryable = [
            m
            for m in pending
            if m.error is not None and m.retry_count < self.max_retries
        ]
        if not retryable:
            return 0

        # Phase 1: Claim messages and hold locks
        acquired: list[tuple[OutboxMessage, ResourceIdentifier, str]] = []

        for msg in retryable:
            resource = ResourceIdentifier("OutboxMessage", msg.message_id)
            try:
                token = await self.lock_strategy.acquire(
                    resource,
                    timeout=0.01,
                    ttl=30.0,
                )
                acquired.append((msg, resource, token))
            except ConcurrencyError:
                continue

        if not acquired:
            return 0

        # Phase 2: Process with held locks
        try:
            published_ids: list[str] = []
            for msg, _, _ in acquired:
                try:
                    await self.publisher.publish(
                        topic=msg.event_type,
                        message=msg.payload,
                        correlation_id=msg.metadata.get("correlation_id"),
                    )
                    published_ids.append(msg.message_id)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Retry failed for outbox message %s: %s",
                        msg.message_id,
                        exc,
                    )
                    await self.storage.mark_failed(msg.message_id, str(exc))

            if published_ids:
                await self.storage.mark_published(published_ids)

            return len(published_ids)

        finally:
            # Release all locks
            for _, resource, token in acquired:
                try:
                    await self.lock_strategy.release(resource, token)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to release lock for %s: %s",
                        resource,
                        exc,
                    )
