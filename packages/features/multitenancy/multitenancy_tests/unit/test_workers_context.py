"""Unit tests for TenantAwareJobWorker."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_advanced_core.background_jobs.entity import BaseBackgroundJob
from cqrs_ddd_multitenancy.context import get_current_tenant_or_none
from cqrs_ddd_multitenancy.workers.context import (
    TenantAwareJobWorker,
    with_tenant_context_from_job,
)

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def tenant_id() -> str:
    """Tenant ID."""
    return "tenant-123"


@pytest.fixture
def job_with_tenant(tenant_id: str) -> BaseBackgroundJob:
    """Create job with tenant metadata."""
    return BaseBackgroundJob.create(
        aggregate_id="job-1",
        job_type="EmailJob",
        total_items=10,
        metadata={"tenant_id": tenant_id},
    )


@pytest.fixture
def job_without_tenant() -> BaseBackgroundJob:
    """Create job without tenant metadata."""
    return BaseBackgroundJob.create(
        aggregate_id="job-2",
        job_type="EmailJob",
        total_items=10,
    )


# ── Test Cases ──────────────────────────────────────────────────────────


class TestTenantAwareJobWorker:
    """Tests for TenantAwareJobWorker wrapper."""

    @pytest.mark.asyncio
    async def test_sets_tenant_context_from_job(
        self, job_with_tenant: BaseBackgroundJob, tenant_id: str
    ) -> None:
        """Should set tenant context from job metadata."""
        tenant_in_handler = None

        async def handler(job: BaseBackgroundJob) -> None:
            nonlocal tenant_in_handler
            tenant_in_handler = get_current_tenant_or_none()

        worker = TenantAwareJobWorker(handler)
        await worker(job_with_tenant)

        assert tenant_in_handler == tenant_id

    @pytest.mark.asyncio
    async def test_resets_tenant_context_after_execution(
        self, job_with_tenant: BaseBackgroundJob
    ) -> None:
        """Should reset tenant context after job execution."""

        async def handler(job: BaseBackgroundJob) -> None:
            pass

        worker = TenantAwareJobWorker(handler)
        await worker(job_with_tenant)

        # Context should be cleared after execution
        assert get_current_tenant_or_none() is None

    @pytest.mark.asyncio
    async def test_resets_context_on_exception(
        self, job_with_tenant: BaseBackgroundJob
    ) -> None:
        """Should reset tenant context even if handler raises exception."""

        async def handler(job: BaseBackgroundJob) -> None:
            raise ValueError("Handler error")

        worker = TenantAwareJobWorker(handler)

        with pytest.raises(ValueError, match="Handler error"):
            await worker(job_with_tenant)

        # Context should be cleared after exception
        assert get_current_tenant_or_none() is None

    @pytest.mark.asyncio
    async def test_executes_without_tenant_if_missing(
        self, job_without_tenant: BaseBackgroundJob, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should execute without tenant context if metadata missing."""
        tenant_in_handler = "should-be-none"

        async def handler(job: BaseBackgroundJob) -> None:
            nonlocal tenant_in_handler
            tenant_in_handler = get_current_tenant_or_none()

        worker = TenantAwareJobWorker(handler)
        await worker(job_without_tenant)

        # Should not have tenant context
        assert tenant_in_handler is None

        # Should log warning
        assert "has no tenant_id in metadata" in caplog.text

    @pytest.mark.asyncio
    async def test_returns_handler_result(
        self, job_with_tenant: BaseBackgroundJob
    ) -> None:
        """Should return the result from handler."""

        async def handler(job: BaseBackgroundJob) -> str:
            return "success"

        worker = TenantAwareJobWorker(handler)
        result = await worker(job_with_tenant)

        assert result == "success"

    @pytest.mark.asyncio
    async def test_custom_tenant_metadata_key(self, tenant_id: str) -> None:
        """Should support custom tenant metadata key."""
        # Create job with custom key
        job = BaseBackgroundJob.create(
            aggregate_id="job-custom",
            job_type="EmailJob",
            total_items=10,
            metadata={"org_id": tenant_id},
        )

        tenant_in_handler = None

        async def handler(job: BaseBackgroundJob) -> None:
            nonlocal tenant_in_handler
            tenant_in_handler = get_current_tenant_or_none()

        worker = TenantAwareJobWorker(handler, tenant_metadata_key="org_id")
        await worker(job)

        assert tenant_in_handler == tenant_id


class TestWithTenantContextFromJob:
    """Tests for with_tenant_context_from_job decorator."""

    @pytest.mark.asyncio
    async def test_decorator_wraps_handler(
        self, job_with_tenant: BaseBackgroundJob, tenant_id: str
    ) -> None:
        """Should wrap handler with tenant context."""

        @with_tenant_context_from_job()
        async def handler(job: BaseBackgroundJob) -> str:
            # Should have tenant context
            assert get_current_tenant_or_none() == tenant_id
            return "success"

        # Handler should be wrapped
        assert isinstance(handler, TenantAwareJobWorker)

        result = await handler(job_with_tenant)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_decorator_with_custom_key(self, tenant_id: str) -> None:
        """Should support custom metadata key via decorator."""

        # Create job with custom key
        job = BaseBackgroundJob.create(
            aggregate_id="job-custom",
            job_type="EmailJob",
            total_items=10,
            metadata={"org_id": tenant_id},
        )

        @with_tenant_context_from_job(tenant_metadata_key="org_id")
        async def handler(job: BaseBackgroundJob) -> None:
            # Should have tenant context
            assert get_current_tenant_or_none() == tenant_id

        await handler(job)

    @pytest.mark.asyncio
    async def test_decorator_resets_context(
        self, job_with_tenant: BaseBackgroundJob
    ) -> None:
        """Should reset context after decorated handler."""

        @with_tenant_context_from_job()
        async def handler(job: BaseBackgroundJob) -> None:
            pass

        await handler(job_with_tenant)

        # Context should be cleared
        assert get_current_tenant_or_none() is None


class TestTenantAwareJobWorkerIntegration:
    """Integration tests for tenant-aware job execution."""

    @pytest.mark.asyncio
    async def test_multiple_jobs_different_tenants(self, tenant_id: str) -> None:
        """Should correctly set context for different tenants."""
        tenant_a = "tenant-a"
        tenant_b = "tenant-b"

        job_a = BaseBackgroundJob.create(
            aggregate_id="job-a",
            job_type="EmailJob",
            total_items=10,
            metadata={"tenant_id": tenant_a},
        )

        job_b = BaseBackgroundJob.create(
            aggregate_id="job-b",
            job_type="EmailJob",
            total_items=10,
            metadata={"tenant_id": tenant_b},
        )

        captured_tenants = []

        async def handler(job: BaseBackgroundJob) -> None:
            captured_tenants.append(get_current_tenant_or_none())

        worker = TenantAwareJobWorker(handler)

        # Execute job for tenant A
        await worker(job_a)

        # Execute job for tenant B
        await worker(job_b)

        # Should have captured different tenants
        assert captured_tenants == [tenant_a, tenant_b]

    @pytest.mark.asyncio
    async def test_nested_contexts_not_supported(
        self, job_with_tenant: BaseBackgroundJob, tenant_id: str
    ) -> None:
        """Should not support nested tenant contexts (one job at a time)."""
        # This test verifies that context is properly reset between jobs

        captured_tenants = []

        async def handler(job: BaseBackgroundJob) -> None:
            # Capture tenant during execution
            captured_tenants.append(get_current_tenant_or_none())

        worker = TenantAwareJobWorker(handler)

        # Execute same job multiple times
        await worker(job_with_tenant)
        await worker(job_with_tenant)

        # Each execution should have the same tenant
        assert captured_tenants == [tenant_id, tenant_id]

        # Context should be cleared after each
        assert get_current_tenant_or_none() is None
