"""BufferedOutbox — unified publisher and background worker for the outbox."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any, cast

from ...ports.background_worker import IBackgroundWorker
from ...ports.messaging import IMessagePublisher
from ...ports.outbox import OutboxMessage
from ...primitives.exceptions import OutboxError
from ..mediator import get_current_uow
from .service import OutboxService

if TYPE_CHECKING:
    from ...ports.locking import ILockStrategy
    from ...ports.outbox import IOutboxStorage

logger = logging.getLogger("cqrs_ddd.outbox")


class BufferedOutbox(IMessagePublisher, IBackgroundWorker):
    """
    Unified Outbox component that handles both recording and publishing.

    Roles:
    1. **Publisher**: Implements ``IMessagePublisher``. Saves messages to DB.
       If used inside a Mediator command scope, it registers a post-commit
       hook to trigger the background loop immediately.
    2. **Worker**: Implements ``IBackgroundWorker``. Runs a debounced background
       loop that batches and publishes messages to the real broker.

    Usage::

        outbox = BufferedOutbox(storage=db_outbox, broker=rabbitmq)
        await outbox.start()

        # In your application
        await outbox.publish("order.created", {"id": 1})
    """

    # Explicitly implement the protocol for structural type checking
    _is_background_worker: IBackgroundWorker = cast("BufferedOutbox", None)

    def __init__(
        self,
        storage: IOutboxStorage | None = None,
        broker: IMessagePublisher | None = None,
        lock_strategy: ILockStrategy | None = None,
        *,
        service: OutboxService | None = None,
        batch_size: int = 50,
        max_retries: int = 5,
        poll_interval: float = 10.0,
        wait_delay: float = 0.1,
        max_delay: float = 1.0,
    ) -> None:
        if service:
            self._service = service
            self._storage = service.storage
            self._broker = service.publisher
        else:
            if storage is None or broker is None or lock_strategy is None:
                raise OutboxError(
                    "Either 'service' or ('storage', 'broker', "
                    "'lock_strategy') must be provided."
                )
            self._storage = storage
            self._broker = broker
            self._service = OutboxService(
                storage, broker, lock_strategy, max_retries=max_retries
            )

        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.wait_delay = wait_delay
        self.max_delay = max_delay

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._trigger_event = asyncio.Event()

    # ── Publisher API ────────────────────────────────────────────────

    async def publish(self, topic: str, message: Any, **kwargs: Any) -> None:
        """Save message to outbox and schedule real-time trigger."""
        # Extract tracing IDs from kwargs
        correlation_id = kwargs.pop("correlation_id", "")
        causation_id = kwargs.pop("causation_id", None)

        if isinstance(message, dict):
            payload = message
        elif hasattr(message, "model_dump"):
            payload = message.model_dump()
        elif hasattr(message, "__dict__"):
            payload = vars(message)
        else:
            payload = {"raw": str(message)}

        outbox_msg = OutboxMessage(
            event_type=topic,
            payload=payload,
            metadata=kwargs,  # Remaining metadata after extracting tracing IDs
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        # Ensure tracing IDs are in metadata for OutboxService when publishing
        outbox_msg.metadata["correlation_id"] = correlation_id
        if causation_id is not None:
            outbox_msg.metadata["causation_id"] = causation_id

        # Get current UoW for transactional consistency
        uow = get_current_uow()

        # Save in same transaction as command/aggregate
        await self._storage.save_messages([outbox_msg], uow=uow)

        # Schedule a trigger after commit
        if uow is not None and hasattr(uow, "on_commit"):
            uow.on_commit(self.trigger)

    def trigger(self) -> None:
        """Wake up the background loop to process messages."""
        self._trigger_event.set()

    # ── Worker Lifecycle ─────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background processing loop."""
        if self._running:
            return
        self._running = True

        # Initial drain (self-healing)
        await self._service.process_batch(self.batch_size * 2)

        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "BufferedOutbox started (batch: %d, wait: %.1fs, fallback: %.1fs)",
            self.batch_size,
            self.wait_delay,
            self.poll_interval,
        )

    async def stop(self) -> None:
        """Stop the background loop gracefully."""
        self._running = False
        self.trigger()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("BufferedOutbox stopped")

    # ── Internal loop ────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        while self._running:
            try:
                # 1. Wait for trigger or polling timeout
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self._trigger_event.wait(), timeout=self.poll_interval
                    )

                # 2. Debouncing
                if self._trigger_event.is_set():
                    await self._debounce()
                    self._trigger_event.clear()

                # 3. Process
                processed = await self._service.process_batch(self.batch_size)

                # 4. If batch full, check for more
                if processed >= self.batch_size:
                    self.trigger()

            except Exception as exc:
                logger.error("BufferedOutbox loop error: %s", exc, exc_info=True)
                await asyncio.sleep(1.0)

    async def _debounce(self) -> None:
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < self.max_delay:
            self._trigger_event.clear()
            try:
                await asyncio.wait_for(
                    self._trigger_event.wait(), timeout=self.wait_delay
                )
            except asyncio.TimeoutError:
                return
