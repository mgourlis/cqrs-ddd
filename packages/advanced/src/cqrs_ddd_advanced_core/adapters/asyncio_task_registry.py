"""AsyncioJobTaskRegistry — IJobKillStrategy for in-process asyncio tasks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from cqrs_ddd_advanced_core.ports.job_runner import IJobKillStrategy

logger = logging.getLogger("cqrs_ddd.background_jobs")


class AsyncioJobTaskRegistry(IJobKillStrategy):
    """Concrete :class:`IJobKillStrategy` for jobs running as asyncio tasks
    in the same process.

    Register each job's :class:`asyncio.Task` when execution starts, and
    unregister when it finishes.  ``request_stop`` cancels the task; asyncio
    has no harder escalation, so ``force_kill`` does the same.

    Example::

        registry = AsyncioJobTaskRegistry()
        task = asyncio.create_task(handler.handle(event))
        registry.register(job.id, task)
        ...
        # Later, from admin:
        await registry.request_stop(job.id)
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def register(self, job_id: str, handle: Any) -> None:
        """Register an ``asyncio.Task`` for a running job."""
        if not isinstance(handle, asyncio.Task):
            raise TypeError(
                f"AsyncioJobTaskRegistry expects asyncio.Task, got {type(handle).__name__}"
            )
        self._tasks[job_id] = handle

    def unregister(self, job_id: str) -> None:
        """Remove a task after the job finishes."""
        self._tasks.pop(job_id, None)

    async def request_stop(self, job_id: str) -> None:
        """Cancel the asyncio task (sends ``CancelledError`` at the next await)."""
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            logger.info("AsyncioJobTaskRegistry: cancelled task for job %s", job_id)

    async def force_kill(self, job_id: str) -> None:
        """Same as ``request_stop`` — asyncio has no harder escalation."""
        await self.request_stop(job_id)
