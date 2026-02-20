"""JobSweeperWorker — reactive background worker for stale job cleanup."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, cast

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry
from cqrs_ddd_core.ports.background_worker import IBackgroundWorker

if TYPE_CHECKING:
    from .service import BackgroundJobService

logger = logging.getLogger("cqrs_ddd.background_jobs")


class JobSweeperWorker(IBackgroundWorker):
    """Reactive worker that sweeps stale/orphaned background jobs.

    Uses trigger + polling fallback. Call :meth:`trigger` to wake immediately
    (e.g. when a job transitions to RUNNING); otherwise runs every
    ``poll_interval`` seconds.

    Implements ``IBackgroundWorker`` (``start`` / ``stop``).
    """

    def __init__(
        self,
        service: BackgroundJobService,
        poll_interval: float = 60.0,
        timeout_seconds: int = 3600,
    ) -> None:
        self._service = service
        self._poll_interval = poll_interval
        self._timeout_seconds = timeout_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._trigger = asyncio.Event()

    def trigger(self) -> None:
        """Wake the worker immediately."""
        self._trigger.set()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "JobSweeperWorker started (poll_interval=%.1fs)",
            self._poll_interval,
        )

    async def stop(self) -> None:
        self._running = False
        self._trigger.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(self._task, timeout=5.0)
        logger.info("JobSweeperWorker stopped")

    async def run_once(self) -> int:
        """Execute a single sweep cycle (useful in tests)."""
        return await self._sweep()

    async def _run_loop(self) -> None:
        while self._running:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._trigger.wait(), timeout=self._poll_interval
                )
            self._trigger.clear()
            try:
                await self._sweep()
            except Exception:
                logger.exception("JobSweeperWorker error")

    async def _sweep(self) -> int:
        registry = get_hook_registry()
        count = cast(
            "int",
            await registry.execute_all(
                "job.sweep.worker",
                {
                    "job.timeout_seconds": self._timeout_seconds,
                    "correlation_id": get_correlation_id(),
                },
                lambda: self._service.process_stale_jobs(
                    timeout_seconds=self._timeout_seconds
                ),
            ),
        )
        if count > 0:
            logger.info("JobSweeperWorker: swept %d stale jobs", count)
        return count
