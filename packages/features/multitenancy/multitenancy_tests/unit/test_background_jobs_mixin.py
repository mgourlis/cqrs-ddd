"""Unit tests for MultitenantBackgroundJobMixin."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_advanced_core.background_jobs.entity import (
    BackgroundJobStatus,
    BaseBackgroundJob,
)
from cqrs_ddd_multitenancy.context import reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import (
    CrossTenantAccessError,
    TenantContextMissingError,
)
from cqrs_ddd_multitenancy.mixins.background_jobs import MultitenantBackgroundJobMixin

# ── Test Doubles ───────────────────────────────────────────────────────


class MockBackgroundJobRepository:
    """Mock base job repository for testing."""

    def __init__(self) -> None:
        self.added_jobs: list[BaseBackgroundJob] = []
        self.updated_jobs: list[BaseBackgroundJob] = []
        self.deleted_jobs: list[BaseBackgroundJob] = []
        self.jobs: dict[str, BaseBackgroundJob] = {}

    async def add(self, job: BaseBackgroundJob) -> None:
        self.added_jobs.append(job)
        self.jobs[job.id] = job

    async def get(self, job_id: str) -> BaseBackgroundJob | None:
        return self.jobs.get(job_id)

    async def update(self, job: BaseBackgroundJob) -> None:
        self.updated_jobs.append(job)
        self.jobs[job.id] = job

    async def delete(self, job: BaseBackgroundJob) -> None:
        self.deleted_jobs.append(job)
        self.jobs.pop(job.id, None)

    async def list_all(
        self,
        entity_ids: list[str] | None = None,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> list[BaseBackgroundJob]:
        jobs = list(self.jobs.values())
        if entity_ids is not None:
            jobs = [j for j in jobs if j.id in entity_ids]
        if specification is not None:
            jobs = [j for j in jobs if specification.is_satisfied_by(j)]
        return jobs

    async def search(
        self, specification: Any, limit: int | None = None, offset: int | None = None
    ):
        """Mock search that returns SearchResult."""
        from cqrs_ddd_core.ports.search_result import SearchResult

        all_jobs = list(self.jobs.values())

        # Simple filtering for mock - in real implementation this would use specification
        if offset:
            all_jobs = all_jobs[offset:]
        if limit:
            all_jobs = all_jobs[:limit]

        result = MagicMock(spec=SearchResult)
        result.list = AsyncMock(return_value=all_jobs)
        return result

    async def get_stale_jobs(
        self,
        timeout_seconds: int | None = None,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> list[BaseBackgroundJob]:
        """Return all RUNNING jobs for simplicity."""
        result = [
            j for j in self.jobs.values() if j.status == BackgroundJobStatus.RUNNING
        ]
        if specification is not None:
            result = [j for j in result if specification.is_satisfied_by(j)]
        return result

    async def find_by_status(
        self,
        statuses: list[BackgroundJobStatus],
        limit: int = 50,
        offset: int = 0,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> list[BaseBackgroundJob]:
        filtered = [j for j in self.jobs.values() if j.status in statuses]
        if specification is not None:
            filtered = [j for j in filtered if specification.is_satisfied_by(j)]
        if offset:
            filtered = filtered[offset:]
        if limit:
            filtered = filtered[:limit]
        return filtered

    async def count_by_status(
        self,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for job in self.jobs.values():
            if specification is not None and not specification.is_satisfied_by(job):
                continue
            status_value = job.status.value
            counts[status_value] = counts.get(status_value, 0) + 1
        return counts

    async def purge_completed(
        self,
        before: datetime,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> int:
        to_delete = [
            j
            for j in self.jobs.values()
            if j.status
            in (BackgroundJobStatus.COMPLETED, BackgroundJobStatus.CANCELLED)
            and j.updated_at < before
        ]
        if specification is not None:
            to_delete = [j for j in to_delete if specification.is_satisfied_by(j)]
        for job in to_delete:
            self.jobs.pop(job.id, None)
        return len(to_delete)

    async def is_cancellation_requested(self, job_id: str, uow: Any = None) -> bool:
        job = self.jobs.get(job_id)
        return job is not None and job.status == BackgroundJobStatus.CANCELLED


class TestMultitenantBackgroundJobRepository(
    MultitenantBackgroundJobMixin, MockBackgroundJobRepository
):
    """Test implementation combining mixin with mock base."""


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def job_repo() -> TestMultitenantBackgroundJobRepository:
    """Create test job repository."""
    return TestMultitenantBackgroundJobRepository()


@pytest.fixture
def tenant_a() -> str:
    """Tenant A ID."""
    return "tenant-a"


@pytest.fixture
def tenant_b() -> str:
    """Tenant B ID."""
    return "tenant-b"


@pytest.fixture
def job_a(tenant_a: str) -> BaseBackgroundJob:
    """Create job for tenant A."""
    return BaseBackgroundJob.create(
        aggregate_id="job-1",
        job_type="EmailJob",
        total_items=10,
        metadata={"tenant_id": tenant_a},
    )


@pytest.fixture
def job_b(tenant_b: str) -> BaseBackgroundJob:
    """Create job for tenant B."""
    return BaseBackgroundJob.create(
        aggregate_id="job-2",
        job_type="EmailJob",
        total_items=10,
        metadata={"tenant_id": tenant_b},
    )


# ── Test Cases ──────────────────────────────────────────────────────────


class TestMultitenantBackgroundJobMixinAdd:
    """Tests for add() method."""

    @pytest.mark.asyncio
    async def test_add_injects_tenant_id(
        self, job_repo: TestMultitenantBackgroundJobRepository, tenant_a: str
    ) -> None:
        """Should inject tenant_id into job metadata."""
        token = set_tenant(tenant_a)
        try:
            job = BaseBackgroundJob.create(
                job_type="EmailJob",
                total_items=10,
            )

            await job_repo.add(job)

            assert len(job_repo.added_jobs) == 1
            assert job_repo.added_jobs[0].metadata.get("tenant_id") == tenant_a
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_add_preserves_existing_tenant_id(
        self, job_repo: TestMultitenantBackgroundJobRepository, tenant_a: str
    ) -> None:
        """Should preserve tenant_id if already in metadata."""
        token = set_tenant(tenant_a)
        try:
            job = BaseBackgroundJob.create(
                job_type="EmailJob",
                total_items=10,
                metadata={"tenant_id": tenant_a},
            )

            await job_repo.add(job)

            assert job_repo.added_jobs[0].metadata.get("tenant_id") == tenant_a
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_add_rejects_cross_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should reject job belonging to different tenant."""
        token = set_tenant(tenant_a)
        try:
            job = BaseBackgroundJob.create(
                job_type="EmailJob",
                total_items=10,
                metadata={"tenant_id": tenant_b},
            )

            with pytest.raises(CrossTenantAccessError):
                await job_repo.add(job)

            assert len(job_repo.added_jobs) == 0
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_add_requires_tenant_context(
        self, job_repo: TestMultitenantBackgroundJobRepository
    ) -> None:
        """Should require tenant context."""
        job = BaseBackgroundJob.create(job_type="EmailJob", total_items=10)

        with pytest.raises(TenantContextMissingError):
            await job_repo.add(job)


class TestMultitenantBackgroundJobMixinGet:
    """Tests for get() method."""

    @pytest.mark.asyncio
    async def test_get_returns_job_for_same_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        tenant_a: str,
    ) -> None:
        """Should return job belonging to current tenant."""
        token = set_tenant(tenant_a)
        try:
            await job_repo.add(job_a)
            result = await job_repo.get(job_a.id)

            assert result is not None
            assert result.id == job_a.id
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_get_returns_none_for_cross_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_b: BaseBackgroundJob,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should return None for cross-tenant access (silent denial)."""
        # Add job in tenant_b's context
        token_b = set_tenant(tenant_b)
        await job_repo.add(job_b)
        reset_tenant(token_b)

        # Try to access from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            result = await job_repo.get(job_b.id)

            assert result is None
        finally:
            reset_tenant(token_a)

    @pytest.mark.asyncio
    async def test_get_returns_none_for_not_found(
        self, job_repo: TestMultitenantBackgroundJobRepository, tenant_a: str
    ) -> None:
        """Should return None if job not found."""
        token = set_tenant(tenant_a)
        try:
            result = await job_repo.get("nonexistent")
            assert result is None
        finally:
            reset_tenant(token)


class TestMultitenantBackgroundJobMixinUpdate:
    """Tests for update() method."""

    @pytest.mark.asyncio
    async def test_update_allows_same_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        tenant_a: str,
    ) -> None:
        """Should allow updating job in same tenant."""
        token = set_tenant(tenant_a)
        try:
            await job_repo.add(job_a)
            job_a.start_processing()
            await job_repo.update(job_a)

            assert len(job_repo.updated_jobs) == 1
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_update_rejects_cross_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_b: BaseBackgroundJob,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should reject updating job from different tenant."""
        # Add job in tenant_b's context
        token_b = set_tenant(tenant_b)
        await job_repo.add(job_b)
        reset_tenant(token_b)

        # Try to update from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            with pytest.raises(CrossTenantAccessError):
                await job_repo.update(job_b)

            assert len(job_repo.updated_jobs) == 0
        finally:
            reset_tenant(token_a)


class TestMultitenantBackgroundJobMixinQueryMethods:
    """Tests for query methods (get_stale_jobs, find_by_status, etc.)."""

    @pytest.mark.asyncio
    async def test_get_stale_jobs_filters_by_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        job_b: BaseBackgroundJob,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should filter stale jobs by tenant."""
        # Start both jobs
        job_a.start_processing()
        job_b.start_processing()

        # Add jobs for both tenants
        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token_b = set_tenant(tenant_b)
        await job_repo.add(job_b)
        reset_tenant(token_b)

        # Query from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            result = await job_repo.get_stale_jobs()

            # Should only return jobs for tenant_a
            assert all(j.metadata.get("tenant_id") == tenant_a for j in result)
        finally:
            reset_tenant(token_a)

    @pytest.mark.asyncio
    async def test_find_by_status_filters_by_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        job_b: BaseBackgroundJob,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should filter jobs by status and tenant."""
        # Complete job_a
        job_a.start_processing()
        job_a.complete({"result": "success"})

        # Add jobs for both tenants
        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token_b = set_tenant(tenant_b)
        await job_repo.add(job_b)
        reset_tenant(token_b)

        # Query from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            result = await job_repo.find_by_status([BackgroundJobStatus.COMPLETED])

            # Should only return completed jobs for tenant_a
            assert len(result) == 1
            assert result[0].id == job_a.id
        finally:
            reset_tenant(token_a)

    @pytest.mark.asyncio
    async def test_count_by_status_filters_by_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        job_b: BaseBackgroundJob,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should count jobs by status for current tenant only."""
        # Complete job_a, leave job_b pending
        job_a.start_processing()
        job_a.complete({"result": "success"})

        # Add jobs for both tenants
        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token_b = set_tenant(tenant_b)
        await job_repo.add(job_b)
        reset_tenant(token_b)

        # Query from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            counts = await job_repo.count_by_status()

            # Should only count tenant_a's jobs
            assert counts.get("COMPLETED", 0) == 1
            assert counts.get("PENDING", 0) == 0  # job_b is not counted
        finally:
            reset_tenant(token_a)

    @pytest.mark.asyncio
    async def test_purge_completed_filters_by_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        job_b: BaseBackgroundJob,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should only purge completed jobs for current tenant."""
        # Complete both jobs
        job_a.start_processing()
        job_a.complete({"result": "success"})

        job_b.start_processing()
        job_b.complete({"result": "success"})

        # Add jobs for both tenants
        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token_b = set_tenant(tenant_b)
        await job_repo.add(job_b)
        reset_tenant(token_b)

        # Purge from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            before = datetime.now(timezone.utc) + timedelta(days=1)
            deleted = await job_repo.purge_completed(before)

            # Should only delete tenant_a's job
            assert deleted == 1
            assert job_a.id not in job_repo.jobs
            assert job_b.id in job_repo.jobs
        finally:
            reset_tenant(token_a)

    @pytest.mark.asyncio
    async def test_is_cancellation_requested_filters_by_tenant(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        job_b: BaseBackgroundJob,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should only check cancellation for current tenant."""
        # Cancel job_a
        job_a.cancel()

        # Add jobs for both tenants
        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token_b = set_tenant(tenant_b)
        await job_repo.add(job_b)
        reset_tenant(token_b)

        # Check from tenant_b (should return False for job_a)
        token_b = set_tenant(tenant_b)
        try:
            is_cancelled = await job_repo.is_cancellation_requested(job_a.id)

            # Should return False because job_a belongs to tenant_a
            assert is_cancelled is False
        finally:
            reset_tenant(token_b)


class TestMultitenantBackgroundJobMixinTenantIsolation:
    """Tests for tenant isolation."""

    @pytest.mark.asyncio
    async def test_different_tenants_jobs_isolated(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        job_b: BaseBackgroundJob,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """Should isolate jobs between tenants."""
        # Add jobs for both tenants
        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token_b = set_tenant(tenant_b)
        await job_repo.add(job_b)
        reset_tenant(token_b)

        # List jobs from tenant_a
        token_a = set_tenant(tenant_a)
        try:
            jobs = await job_repo.list_all()

            # Should only see tenant_a's job
            assert len(jobs) == 1
            assert jobs[0].id == job_a.id
        finally:
            reset_tenant(token_a)

        # List jobs from tenant_b
        token_b = set_tenant(tenant_b)
        try:
            jobs = await job_repo.list_all()

            # Should only see tenant_b's job
            assert len(jobs) == 1
            assert jobs[0].id == job_b.id
        finally:
            reset_tenant(token_b)


class TestMultitenantBackgroundJobMixinSystemTenant:
    """Tests for system tenant bypass."""

    @pytest.mark.asyncio
    async def test_add_system_tenant_bypasses(
        self, job_repo: TestMultitenantBackgroundJobRepository
    ) -> None:
        """System tenant should bypass tenant injection."""
        from cqrs_ddd_multitenancy.context import SYSTEM_TENANT

        token = set_tenant(SYSTEM_TENANT)
        try:
            job = BaseBackgroundJob.create(job_type="EmailJob", total_items=10)
            await job_repo.add(job)
            assert len(job_repo.added_jobs) == 1
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_get_system_tenant_bypasses(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        tenant_a: str,
    ) -> None:
        """System tenant should see any job."""
        from cqrs_ddd_multitenancy.context import SYSTEM_TENANT

        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token = set_tenant(SYSTEM_TENANT)
        try:
            result = await job_repo.get(job_a.id)
            assert result is not None
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_delete_system_tenant_bypasses(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        tenant_a: str,
    ) -> None:
        """System tenant should delete any job."""
        from cqrs_ddd_multitenancy.context import SYSTEM_TENANT

        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token = set_tenant(SYSTEM_TENANT)
        try:
            await job_repo.delete(job_a)
            assert len(job_repo.deleted_jobs) == 1
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_update_system_tenant_bypasses(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        tenant_a: str,
    ) -> None:
        """System tenant should update any job."""
        from cqrs_ddd_multitenancy.context import SYSTEM_TENANT

        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token = set_tenant(SYSTEM_TENANT)
        try:
            await job_repo.update(job_a)
            assert len(job_repo.updated_jobs) == 1
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_list_all_system_tenant_returns_all(
        self,
        job_repo: TestMultitenantBackgroundJobRepository,
        job_a: BaseBackgroundJob,
        job_b: BaseBackgroundJob,
        tenant_a: str,
        tenant_b: str,
    ) -> None:
        """System tenant should list all jobs."""
        from cqrs_ddd_multitenancy.context import SYSTEM_TENANT

        token_a = set_tenant(tenant_a)
        await job_repo.add(job_a)
        reset_tenant(token_a)

        token_b = set_tenant(tenant_b)
        await job_repo.add(job_b)
        reset_tenant(token_b)

        token = set_tenant(SYSTEM_TENANT)
        try:
            jobs = await job_repo.list_all()
            assert len(jobs) == 2
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_tenant_id_set_on_dedicated_field(
        self, job_repo: TestMultitenantBackgroundJobRepository, tenant_a: str
    ) -> None:
        """Should set tenant_id on both dedicated field and metadata."""
        token = set_tenant(tenant_a)
        try:
            job = BaseBackgroundJob.create(job_type="EmailJob", total_items=5)
            await job_repo.add(job)
            assert job.tenant_id == tenant_a
            assert job.metadata.get("tenant_id") == tenant_a
        finally:
            reset_tenant(token)
