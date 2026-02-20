"""SagaRecoveryWorker — reactive worker for stale/timed-out sagas."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry
from cqrs_ddd_core.ports.background_worker import IBackgroundWorker

if TYPE_CHECKING:
    from .manager import SagaManager

logger = logging.getLogger("cqrs_ddd.sagas")


class SagaRecoveryWorker(IBackgroundWorker):
    """
    Reactive background worker for saga recovery.

    Uses event-driven trigger plus polling fallback (same pattern as
    BufferedOutbox). Call :meth:`trigger` to wake immediately (e.g. when
    a saga stalls); otherwise the worker runs every ``poll_interval`` seconds.

    Implements ``IBackgroundWorker`` (``start`` / ``stop``).
    """

    def __init__(
        self,
        saga_manager: SagaManager,
        poll_interval: float = 60.0,
        timeout_batch_size: int = 10,
        recovery_batch_size: int = 10,
    ) -> None:
        self.saga_manager = saga_manager
        self._poll_interval = poll_interval
        self.timeout_batch_size = timeout_batch_size
        self.recovery_batch_size = recovery_batch_size
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._trigger = asyncio.Event()

    def trigger(self) -> None:
        """Wake the worker immediately (e.g. after a saga stalls)."""
        self._trigger.set()

    async def start(self) -> None:
        """Start the background loop."""
        if self._running:
            logger.warning("SagaRecoveryWorker already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "SagaRecoveryWorker started (poll_interval=%.1fs)",
            self._poll_interval,
        )

    async def stop(self) -> None:
        """Stop the background loop gracefully."""
        if not self._running:
            return
        self._running = False
        self._trigger.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("SagaRecoveryWorker stopped")

    async def _run_loop(self) -> None:
        while self._running:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._trigger.wait(), timeout=self._poll_interval
                )
            self._trigger.clear()
            try:
                await self._process_cycle()
            except Exception as exc:  # noqa: BLE001
                logger.error("Error in SagaRecoveryWorker cycle: %s", exc)

    async def _process_cycle(self) -> None:
        """Run one timeout + recovery cycle."""
        try:
            await self.saga_manager.process_timeouts(limit=self.timeout_batch_size)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error processing timeouts: %s", exc)

        try:
            await self.saga_manager.process_tcc_timeouts(limit=self.timeout_batch_size)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error processing TCC timeouts: %s", exc)

        try:
            await self.saga_manager.recover_pending_sagas(
                limit=self.recovery_batch_size
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Error recovering pending sagas: %s", exc)

    async def run_once(self) -> None:
        """Execute a single cycle (tests or manual trigger)."""
        registry = get_hook_registry()
        await registry.execute_all(
            "saga.recovery.run_once",
            {"correlation_id": get_correlation_id()},
            self._process_cycle,
        )
