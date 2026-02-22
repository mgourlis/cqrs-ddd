"""InMemoryBackgroundJobRepository — in-memory implementation for testing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cqrs_ddd_advanced_core.background_jobs.entity import (
    BackgroundJobStatus,
    BaseBackgroundJob,
)
from cqrs_ddd_advanced_core.ports.background_jobs import IBackgroundJobRepository
from cqrs_ddd_core.ports.search_result import SearchResult

if TYPE_CHECKING:
    import builtins
    from collections.abc import AsyncIterator

    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

_TERMINAL_STATUSES = frozenset(
    {BackgroundJobStatus.COMPLETED, BackgroundJobStatus.CANCELLED}
)


class InMemoryBackgroundJobRepository(IBackgroundJobRepository):
    """In-memory implementation of ``IBackgroundJobRepository`` for testing."""

    def __init__(self) -> None:
        self._jobs: dict[str, BaseBackgroundJob] = {}

    async def add(
        self, entity: BaseBackgroundJob, _uow: UnitOfWork | None = None
    ) -> str:
        """Store or update a job."""
        # Simulate database version increment
        object.__setattr__(entity, "_version", entity.version + 1)
        self._jobs[entity.id] = entity
        return entity.id

    async def get(
        self, entity_id: str, _uow: UnitOfWork | None = None
    ) -> BaseBackgroundJob | None:
        """Retrieve a job by ID."""
        return self._jobs.get(entity_id)

    async def delete(self, entity_id: str, _uow: UnitOfWork | None = None) -> str:
        """Delete a job by ID."""
        self._jobs.pop(entity_id, None)
        return entity_id

    async def list_all(
        self,
        entity_ids: builtins.list[str] | None = None,
        _uow: UnitOfWork | None = None,
    ) -> builtins.list[BaseBackgroundJob]:
        """Retrieve all jobs, or filter by IDs."""
        if entity_ids is None:
            return list(self._jobs.values())
        return [j for jid, j in self._jobs.items() if jid in entity_ids]

    async def search(
        self,
        criteria: ISpecification[BaseBackgroundJob] | object,
        _uow: UnitOfWork | None = None,
    ) -> SearchResult[BaseBackgroundJob]:
        """Search for jobs matching the specification."""
        from cqrs_ddd_core.domain.specification import ISpecification as ISpec

        spec = criteria if isinstance(criteria, ISpec) else criteria

        async def _list() -> builtins.list[BaseBackgroundJob]:
            return [j for j in self._jobs.values() if spec.is_satisfied_by(j)]  # type: ignore[attr-defined]

        async def _stream(_batch_size: int | None) -> AsyncIterator[BaseBackgroundJob]:
            for j in self._jobs.values():
                if spec.is_satisfied_by(j):  # type: ignore[attr-defined]
                    yield j

        return SearchResult(list_fn=_list, stream_fn=_stream)

    async def get_stale_jobs(
        self, timeout_seconds: int | None = None, _uow: UnitOfWork | None = None
    ) -> builtins.list[BaseBackgroundJob]:
        """Fetch jobs in RUNNING state that have exceeded timeout."""
        stale = []
        now = datetime.now(timezone.utc)

        for job in self._jobs.values():
            if job.status != BackgroundJobStatus.RUNNING:
                continue

            updated = job.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)

            elapsed = (now - updated).total_seconds()
            timeout = timeout_seconds if timeout_seconds is not None else 3600

            if elapsed > timeout:
                stale.append(job)

        return stale

    async def find_by_status(
        self,
        statuses: builtins.list[BackgroundJobStatus],
        limit: int = 50,
        offset: int = 0,
        _uow: UnitOfWork | None = None,
    ) -> builtins.list[BaseBackgroundJob]:
        """Return jobs matching given statuses, ordered by updated_at desc."""
        status_set = set(statuses)

        def _sort_key(j: BaseBackgroundJob) -> datetime:
            # Normalize to UTC-aware so that mixed naive/aware jobs sort correctly.
            ts = j.updated_at
            return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)

        matched = sorted(
            (j for j in self._jobs.values() if j.status in status_set),
            key=_sort_key,
            reverse=True,
        )
        return matched[offset : offset + limit]

    async def count_by_status(
        self,
        _uow: UnitOfWork | None = None,
    ) -> builtins.dict[str, int]:
        """Return a mapping of status value → job count (omits zero-count statuses)."""
        counts: builtins.dict[str, int] = {}
        for job in self._jobs.values():
            key = job.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    async def is_cancellation_requested(
        self,
        job_id: str,
        _uow: UnitOfWork | None = None,
    ) -> bool:
        """Return True if the job's stored status is CANCELLED."""
        job = self._jobs.get(job_id)
        return job is not None and job.status == BackgroundJobStatus.CANCELLED

    async def purge_completed(
        self,
        before: datetime,
        _uow: UnitOfWork | None = None,
    ) -> int:
        """Delete COMPLETED and CANCELLED jobs with updated_at older than before."""
        if before.tzinfo is None:
            before = before.replace(tzinfo=timezone.utc)

        to_delete = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in _TERMINAL_STATUSES
            and (
                job.updated_at.replace(tzinfo=timezone.utc)
                if job.updated_at.tzinfo is None
                else job.updated_at
            )
            < before
        ]
        for job_id in to_delete:
            del self._jobs[job_id]
        return len(to_delete)
