"""BackgroundJobAdminService — administrative operations over background jobs."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cqrs_ddd_advanced_core.exceptions import JobStateError

from .entity import BackgroundJobStatus

if TYPE_CHECKING:
    from ..ports.background_jobs import IBackgroundJobRepository
    from ..ports.job_runner import IJobKillStrategy
    from .entity import BaseBackgroundJob

logger = logging.getLogger("cqrs_ddd.background_jobs.admin")


@dataclass(frozen=True)
class JobStatistics:
    """Snapshot of background job counts, suitable for dashboards and health checks.

    Attributes:
        counts: Mapping of ``BackgroundJobStatus`` value → job count.
            Statuses with zero jobs are omitted.
        total: Sum of all counts across all statuses.
    """

    counts: dict[str, int] = field(default_factory=dict)
    total: int = 0


class BackgroundJobAdminService:
    """Administrative service for background job operations.

    Provides listing, statistics, bulk mutations, and cleanup; all through
    ``IBackgroundJobRepository``.  Intentionally separate from
    ``BackgroundJobService``, which owns the operational path (sweep,
    schedule, mark-running).

    Example::

        admin = BackgroundJobAdminService(repository)

        # Dashboard stats
        stats = await admin.get_statistics()
        print(stats.counts)  # {"PENDING": 12, "FAILED": 3, ...}

        # Paginated listing
        failed = await admin.list_jobs([BackgroundJobStatus.FAILED], limit=20)

        # Bulk retry all failed jobs (up to 100)
        retried, skipped = await admin.bulk_retry([j.id for j in failed])

        # Cleanup old completed jobs
        cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc)
        deleted = await admin.purge_completed(before=cutoff)
    """

    def __init__(self, repository: IBackgroundJobRepository) -> None:
        self._repository = repository

    async def list_jobs(
        self,
        statuses: list[BackgroundJobStatus] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BaseBackgroundJob]:
        """Return jobs filtered by status with pagination.

        Args:
            statuses: Filter to these statuses. If ``None`` or empty, returns
                jobs in all statuses (uses ``list_all`` internally).
            limit: Maximum results. Ignored when ``statuses`` is ``None`` or empty.
            offset: Skip this many results. Ignored when ``statuses`` is ``None``
                or empty.

        Returns:
            List of matching jobs ordered by ``updated_at`` descending.
        """
        if not statuses:
            return await self._repository.list_all()
        return await self._repository.find_by_status(
            statuses, limit=limit, offset=offset
        )

    async def get_statistics(self) -> JobStatistics:
        """Return aggregated counts per status.

        Returns:
            A :class:`JobStatistics` value object with per-status counts and
            the overall total.
        """
        counts = await self._repository.count_by_status()
        total = sum(counts.values())
        return JobStatistics(counts=counts, total=total)

    async def bulk_cancel(self, job_ids: list[str]) -> tuple[int, int]:
        """Cancel multiple jobs by ID.

        Only jobs in a cancellable state (PENDING or RUNNING) are mutated.
        Jobs that cannot be cancelled (e.g. already COMPLETED) are skipped
        silently with a debug log entry.

        Args:
            job_ids: IDs of jobs to cancel.

        Returns:
            ``(cancelled, skipped)`` counts.
        """
        cancelled = skipped = 0
        for job_id in job_ids:
            job = await self._repository.get(job_id)
            if job is None:
                logger.debug("bulk_cancel: job %s not found — skipping", job_id)
                skipped += 1
                continue
            if job.status in (
                BackgroundJobStatus.COMPLETED,
                BackgroundJobStatus.CANCELLED,
            ):
                logger.debug(
                    "bulk_cancel: job %s already terminal (%s) — skipping",
                    job_id,
                    job.status.value,
                )
                skipped += 1
                continue
            try:
                job.cancel()
                await self._repository.add(job)
                cancelled += 1
            except Exception:
                logger.exception("bulk_cancel: failed to cancel job %s", job_id)
                skipped += 1
        return cancelled, skipped

    async def cancel_running(
        self,
        job_id: str,
        kill_strategy: IJobKillStrategy | None = None,
        grace_seconds: float = 30.0,
    ) -> BaseBackgroundJob | None:
        """Cancel a RUNNING job with optional escalation to runtime kill.

        1. Marks the job CANCELLED in the repository (cooperative signal).
        2. If ``kill_strategy`` is provided, sends a graceful stop signal.
        3. Polls the repository for up to ``grace_seconds`` waiting for the
           handler to acknowledge cancellation.
        4. If still alive after the grace period, force-kills and marks FAILED.

        Without a ``kill_strategy``, the method returns immediately after
        persisting the CANCELLED state — the handler must detect it via
        :meth:`~BackgroundJobEventHandler.checkpoint_cancellation`.

        Args:
            job_id: ID of the job to cancel.
            kill_strategy: Optional runtime-level kill mechanism.
            grace_seconds: Seconds to wait for graceful shutdown before
                force-killing.  Ignored when ``kill_strategy`` is ``None``.

        Returns:
            The job in its final state, or ``None`` if not found.
        """
        job = await self._repository.get(job_id)
        if job is None:
            return None

        if job.status != BackgroundJobStatus.RUNNING:
            logger.debug(
                "cancel_running: job %s is %s (not RUNNING) — returning as-is",
                job_id,
                job.status.value,
            )
            return job

        # Layer 1: mark CANCELLED in persistence (cooperative signal)
        job.cancel()
        await self._repository.add(job)
        logger.info("cancel_running: job %s marked CANCELLED", job_id)

        if kill_strategy is None:
            return job

        # Layer 2: escalation via runtime kill strategy
        await kill_strategy.request_stop(job_id)
        logger.info(
            "cancel_running: sent stop signal to job %s, "
            "waiting up to %.0fs for graceful shutdown",
            job_id,
            grace_seconds,
        )

        elapsed = 0.0
        poll_interval = 1.0
        while elapsed < grace_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            latest = await self._repository.get(job_id)
            if not latest:
                return None
            if latest.status != BackgroundJobStatus.RUNNING:
                logger.info(
                    "cancel_running: job %s stopped gracefully (%s)",
                    job_id,
                    latest.status.value,
                )
                return latest

        # Grace period expired — force kill
        logger.warning(
            "cancel_running: job %s did not stop within %.0fs — force killing",
            job_id,
            grace_seconds,
        )
        await kill_strategy.force_kill(job_id)

        latest = await self._repository.get(job_id)
        if latest and latest.status == BackgroundJobStatus.RUNNING:
            latest.fail(
                f"Terminated: did not stop within {grace_seconds:.0f}s grace period"
            )
            await self._repository.add(latest)
        return latest

    async def bulk_retry(self, job_ids: list[str]) -> tuple[int, int]:
        """Retry multiple FAILED jobs by ID.

        Only FAILED jobs within their ``max_retries`` budget are mutated.
        Jobs in any other state are skipped silently.

        Args:
            job_ids: IDs of FAILED jobs to retry.

        Returns:
            ``(retried, skipped)`` counts.
        """
        retried = skipped = 0
        for job_id in job_ids:
            job = await self._repository.get(job_id)
            if job is None:
                logger.debug("bulk_retry: job %s not found — skipping", job_id)
                skipped += 1
                continue
            if job.status != BackgroundJobStatus.FAILED:
                logger.debug(
                    "bulk_retry: job %s is %s (not FAILED) — skipping",
                    job_id,
                    job.status.value,
                )
                skipped += 1
                continue
            if job.retry_count >= job.max_retries:
                logger.warning(
                    "bulk_retry: job %s has exhausted retries (%d/%d) — skipping",
                    job_id,
                    job.retry_count,
                    job.max_retries,
                )
                skipped += 1
                continue
            try:
                job.retry()
                await self._repository.add(job)
                retried += 1
            except JobStateError:
                # Race: state changed between load and retry.
                logger.warning(
                    "bulk_retry: job %s state changed concurrently — skipping", job_id
                )
                skipped += 1
            except Exception:
                logger.exception("bulk_retry: unexpected error retrying job %s", job_id)
                skipped += 1
        return retried, skipped

    async def purge_completed(
        self,
        before: datetime | None = None,
    ) -> int:
        """Delete COMPLETED and CANCELLED jobs updated before ``before``.

        Args:
            before: UTC cutoff datetime. Defaults to now (purges all terminal jobs).

        Returns:
            Number of jobs deleted.
        """
        threshold = before if before is not None else datetime.now(timezone.utc)
        # Always pass a timezone-aware datetime so both SQLAlchemy and in-memory
        # adapters compare against the same reference frame.
        if threshold.tzinfo is None:
            threshold = threshold.replace(tzinfo=timezone.utc)
        deleted = await self._repository.purge_completed(threshold)
        if deleted:
            logger.info(
                "purge_completed: deleted %d terminal jobs (before=%s)",
                deleted,
                threshold.isoformat(),
            )
        return deleted
