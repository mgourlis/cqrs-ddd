"""Tenant-aware job worker wrapper for context propagation.

This module provides utilities for propagating tenant context to background
job workers, ensuring jobs execute in the correct tenant context.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..context import Token, reset_tenant, set_tenant

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.background_jobs.entity import BaseBackgroundJob

__all__ = [
    "TenantAwareJobWorker",
    "with_tenant_context_from_job",
]

logger = logging.getLogger(__name__)


class TenantAwareJobWorker:
    """Wrapper for background job workers with tenant context propagation.

    This wrapper ensures that when a job is executed by a worker, the tenant
    context is automatically set from the job's metadata before execution and
    reset after completion.

    Usage:
        ```python
        # Wrap your job handler
        async def my_job_handler(job: BaseBackgroundJob) -> None:
            # Job executes in tenant context
            ...

        # Create tenant-aware wrapper
        tenant_aware_handler = TenantAwareJobWorker(my_job_handler)

        # Use with job runner
        await job_runner.register_handler("MyJobType", tenant_aware_handler)
        ```

    The wrapper extracts the tenant_id from the job's metadata and sets it
    as the current tenant context for the duration of job execution.
    """

    def __init__(
        self,
        handler: Callable[[BaseBackgroundJob], Any],
        tenant_metadata_key: str = "tenant_id",
    ) -> None:
        """Initialize the tenant-aware worker.

        Args:
            handler: The actual job handler to wrap.
            tenant_metadata_key: The metadata key for tenant ID (default: "tenant_id").
        """
        self.handler = handler
        self.tenant_metadata_key = tenant_metadata_key

    async def __call__(self, job: BaseBackgroundJob) -> Any:
        """Execute the job with tenant context propagation.

        Args:
            job: The job to execute.

        Returns:
            The result of the job handler.
        """
        # Extract tenant_id from job metadata
        tenant_id = job.metadata.get(self.tenant_metadata_key)

        if tenant_id is None:
            logger.warning(
                f"Job {job.id} has no tenant_id in metadata. "
                "Executing without tenant context."
            )
            # Execute without tenant context
            return await self.handler(job)

        # Set tenant context and execute
        token: Token[str | None] | None = None
        try:
            token = set_tenant(tenant_id)
            logger.debug(f"Set tenant context for job {job.id}: tenant_id={tenant_id}")
            return await self.handler(job)
        finally:
            if token is not None:
                reset_tenant(token)
                logger.debug(f"Reset tenant context for job {job.id}")


def with_tenant_context_from_job(
    tenant_metadata_key: str = "tenant_id",
) -> Callable[[Callable[[BaseBackgroundJob], Any]], TenantAwareJobWorker]:
    """Decorator factory for wrapping job handlers with tenant context.

    Usage:
        ```python
        @with_tenant_context_from_job()
        async def my_job_handler(job: BaseBackgroundJob) -> None:
            # Job executes in tenant context
            ...

        # Or with custom metadata key
        @with_tenant_context_from_job(tenant_metadata_key="org_id")
        async def my_job_handler(job: BaseBackgroundJob) -> None:
            ...
        ```

    Args:
        tenant_metadata_key: The metadata key for tenant ID (default: "tenant_id").

    Returns:
        A decorator function that wraps the handler.
    """

    def decorator(handler: Callable[[BaseBackgroundJob], Any]) -> TenantAwareJobWorker:
        return TenantAwareJobWorker(handler, tenant_metadata_key)

    return decorator
