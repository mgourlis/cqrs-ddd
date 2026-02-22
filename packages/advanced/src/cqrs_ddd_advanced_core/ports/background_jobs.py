"""IBackgroundJobRepository — repository port for background jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cqrs_ddd_core.ports.repository import IRepository

if TYPE_CHECKING:
    import builtins
    from datetime import datetime

    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from ..background_jobs.entity import BackgroundJobStatus, BaseBackgroundJob


@runtime_checkable
class IBackgroundJobRepository(IRepository["BaseBackgroundJob", str], Protocol):
    """Repository interface for background jobs, following IRepository pattern.

    Infrastructure packages (SQLAlchemy, Mongo, …) provide the real
    implementation; ``InMemoryBackgroundJobRepository`` ships in the
    ``adapters.memory`` module for unit tests.

    Operational queries (used by workers):
        - ``get_stale_jobs`` — find timed-out RUNNING jobs for the sweeper.

    Administrative queries (used by dashboards / CLI / admin services):
        - ``find_by_status`` — paginated listing by lifecycle status.
        - ``count_by_status`` — aggregate counts per status for dashboards.
        - ``purge_completed`` — bulk-delete terminal jobs older than a threshold.
    """

    async def get_stale_jobs(
        self, timeout_seconds: int | None = None, uow: UnitOfWork | None = None
    ) -> builtins.list[BaseBackgroundJob]:
        """Fetch RUNNING jobs that have exceeded their timeout.

        Args:
            timeout_seconds: Override the default timeout.
                If None, uses repository default.
            uow: Optional UnitOfWork to use.
        """
        ...

    async def find_by_status(
        self,
        statuses: builtins.list[BackgroundJobStatus],
        limit: int = 50,
        offset: int = 0,
        uow: UnitOfWork | None = None,
    ) -> builtins.list[BaseBackgroundJob]:
        """Return jobs matching any of the given statuses, with pagination.

        Results are ordered by ``updated_at`` descending (most recent first).

        Args:
            statuses: One or more ``BackgroundJobStatus`` values to filter by.
            limit: Maximum number of results to return.
            offset: Number of results to skip (for pagination).
            uow: Optional UnitOfWork to use.
        """
        ...

    async def count_by_status(
        self,
        uow: UnitOfWork | None = None,
    ) -> builtins.dict[str, int]:
        """Return a mapping of status value → job count across all statuses.

        Statuses with zero jobs are omitted from the result.

        Args:
            uow: Optional UnitOfWork to use.
        """
        ...

    async def purge_completed(
        self,
        before: datetime,
        uow: UnitOfWork | None = None,
    ) -> int:
        """Delete COMPLETED and CANCELLED jobs whose ``updated_at`` precedes ``before``.

        Args:
            before: UTC datetime threshold; jobs updated before this are deleted.
            uow: Optional UnitOfWork to use.

        Returns:
            Number of jobs deleted.
        """
        ...

    async def is_cancellation_requested(
        self,
        job_id: str,
        uow: UnitOfWork | None = None,
    ) -> bool:
        """Check whether the job's persisted status is CANCELLED.

        Designed for lightweight polling inside long-running handlers
        (cooperative cancellation checkpoints). Implementations should
        query only the status column, not load the full aggregate.

        Args:
            job_id: ID of the job to check.
            uow: Optional UnitOfWork to use.

        Returns:
            True if the stored status is CANCELLED, False otherwise
            (including when the job does not exist).
        """
        ...
