"""BackgroundJobService — schedule, cancel, retry, and sweep stale jobs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..ports.background_jobs import IBackgroundJobRepository
    from .entity import BaseBackgroundJob

logger = logging.getLogger("cqrs_ddd.background_jobs")


class BackgroundJobService:
    """Core service for background-job operations.

    Acts as a bridge between business logic and the persistence layer.
    All persistence goes through ``IBackgroundJobRepository``.

    Optional ``sweeper_trigger``: call :meth:`set_sweeper_trigger` with
    ``JobSweeperWorker.trigger`` so the sweeper wakes when a job becomes
    RUNNING (e.g. via :meth:`mark_running`).
    """

    def __init__(
        self,
        persistence: IBackgroundJobRepository,
        sweeper_trigger: Callable[[], None] | None = None,
    ) -> None:
        self._persistence = persistence
        self._sweeper_trigger = sweeper_trigger

    def set_sweeper_trigger(self, callback: Callable[[], None] | None) -> None:
        """Set or clear the callback invoked when a job becomes RUNNING.

        E.g. JobSweeperWorker.trigger.
        """
        self._sweeper_trigger = callback

    # -- commands ---------------------------------------------------------

    async def schedule(
        self,
        job: BaseBackgroundJob,
    ) -> BaseBackgroundJob:
        """Persist a newly created job (status PENDING)."""
        registry = get_hook_registry()
        attributes = {
            "job.type": type(job).__name__,
            "job.id": str(getattr(job, "id", "")),
            "message_type": type(job),
            "correlation_id": get_correlation_id()
            or getattr(job, "correlation_id", None),
        }
        return cast(
            "BaseBackgroundJob",
            await registry.execute_all(
                f"job.enqueue.{type(job).__name__}",
                attributes,
                lambda: self._schedule_internal(job),
            ),
        )

    async def _schedule_internal(self, job: BaseBackgroundJob) -> BaseBackgroundJob:
        await self._persistence.add(job)
        return job

    async def cancel(
        self,
        job_id: str,
    ) -> BaseBackgroundJob | None:
        """Cancel a job if it is still in a cancellable state."""
        job = await self._persistence.get(job_id)
        if not job:
            return None

        job.cancel()
        await self._persistence.add(job)
        return job

    async def retry(
        self,
        job_id: str,
    ) -> BaseBackgroundJob | None:
        """Retry a failed job."""
        job = await self._persistence.get(job_id)
        if not job:
            return None

        job.retry()
        await self._persistence.add(job)
        return job

    async def get(
        self,
        job_id: str,
    ) -> BaseBackgroundJob | None:
        """Fetch a single job by ID."""
        return await self._persistence.get(job_id)

    async def mark_running(self, job_id: str) -> BaseBackgroundJob | None:
        """Transition a PENDING job to RUNNING and persist. Wakes sweeper if set."""
        job = await self._persistence.get(job_id)
        if not job:
            return None
        job.start_processing()
        await self._persistence.add(job)
        if self._sweeper_trigger is not None:
            try:
                self._sweeper_trigger()
            except Exception:  # noqa: BLE001
                logger.debug("Sweeper trigger failed", exc_info=True)
        return job

    # -- sweeping ---------------------------------------------------------

    async def process_stale_jobs(self, timeout_seconds: int = 3600) -> int:
        """Mark stale/timed-out jobs as FAILED.

        Returns the number of jobs swept.
        """
        registry = get_hook_registry()
        return cast(
            "int",
            await registry.execute_all(
                "job.sweep.stale",
                {
                    "job.timeout_seconds": timeout_seconds,
                    "correlation_id": get_correlation_id(),
                },
                lambda: self._process_stale_jobs_internal(timeout_seconds),
            ),
        )

    async def _process_stale_jobs_internal(self, timeout_seconds: int = 3600) -> int:
        stale_jobs = await self._persistence.get_stale_jobs(
            timeout_seconds=timeout_seconds
        )
        if not stale_jobs:
            return 0

        swept = 0
        for job in stale_jobs:
            try:
                job.fail(f"Job timed out after {timeout_seconds}s (stale)")
                await self._persistence.add(job)
                swept += 1
            except Exception:
                logger.exception(
                    "Failed to sweep stale job %s",
                    getattr(job, "id", "unknown"),
                )
        return swept
