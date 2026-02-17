"""CommandSchedulerWorker — reactive background worker for due scheduled commands."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from cqrs_ddd_core.ports.background_worker import IBackgroundWorker

if TYPE_CHECKING:
    from .service import CommandSchedulerService

logger = logging.getLogger("cqrs_ddd.scheduling")


class CommandSchedulerWorker(IBackgroundWorker):
    """Reactive worker that executes due scheduled commands.

    Uses trigger + polling fallback. Call :meth:`trigger` to wake immediately
    (e.g. when a command is scheduled); otherwise runs every
    ``poll_interval`` seconds.

    Implements ``IBackgroundWorker`` (``start`` / ``stop``).
    """

    def __init__(
        self,
        service: CommandSchedulerService,
        poll_interval: float = 60.0,
    ) -> None:
        self._service = service
        self._poll_interval = poll_interval
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
            "CommandSchedulerWorker started (poll_interval=%.1fs)",
            self._poll_interval,
        )

    async def stop(self) -> None:
        self._running = False
        self._trigger.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(self._task, timeout=5.0)
        logger.info("CommandSchedulerWorker stopped")

    async def run_once(self) -> int:
        """Execute a single processing cycle (useful in tests)."""
        return await self._process()

    async def _run_loop(self) -> None:
        while self._running:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._trigger.wait(), timeout=self._poll_interval
                )
            self._trigger.clear()
            try:
                await self._process()
            except Exception:
                logger.exception("CommandSchedulerWorker error")

    async def _process(self) -> int:
        count = await self._service.process_due_commands()
        if count > 0:
            logger.info("CommandSchedulerWorker: executed %d due commands", count)
        return count
