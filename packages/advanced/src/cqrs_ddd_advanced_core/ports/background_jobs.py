"""IBackgroundJobRepository — repository port for background jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cqrs_ddd_core.ports.repository import IRepository

if TYPE_CHECKING:
    import builtins

    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from ..background_jobs.entity import BaseBackgroundJob


@runtime_checkable
class IBackgroundJobRepository(IRepository["BaseBackgroundJob", str], Protocol):
    """
    Repository interface for background jobs, following IRepository pattern.

    Infrastructure packages (SQLAlchemy, Mongo, …) provide the real
    implementation; ``InMemoryBackgroundJobRepository`` ships in the
    ``background_jobs.testing`` module for unit tests.
    """

    async def get_stale_jobs(
        self, timeout_seconds: int | None = None, uow: UnitOfWork | None = None
    ) -> builtins.list[BaseBackgroundJob]:
        """Fetch jobs that are 'running' but have exceeded their timeout.

        Args:
            timeout_seconds: Override the default timeout.
                If None, uses repository default.
            uow: Optional UnitOfWork to use.
        """
        ...
