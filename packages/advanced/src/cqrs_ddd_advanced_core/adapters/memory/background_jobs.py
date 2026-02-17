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

            # Ensure updated_at is UTC
            updated = job.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)

            elapsed = (now - updated).total_seconds()

            # Use override if provided, else default to 1 hour
            timeout = timeout_seconds if timeout_seconds is not None else 3600

            if elapsed > timeout:
                stale.append(job)

        return stale
