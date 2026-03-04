"""Multitenant background job repository mixin for automatic tenant filtering.

This mixin automatically injects tenant_id filters into all background job
repository operations when composed with a base repository class via MRO.

Filtering is pushed to the persistence layer via specification
composition — no in-memory post-fetch filtering.

Usage:
    class MyJobRepository(MultitenantBackgroundJobMixin, SQLAlchemyBackgroundJobRepository):
        pass

The mixin must appear BEFORE the base repository in the MRO to ensure
method resolution overrides the base methods correctly.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..context import get_current_tenant_or_none, is_system_tenant
from ..exceptions import CrossTenantAccessError, TenantContextMissingError

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.background_jobs.entity import (
        BackgroundJobStatus,
        BaseBackgroundJob,
    )
    from cqrs_ddd_core.ports.search_result import SearchResult
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

__all__ = [
    "MultitenantBackgroundJobMixin",
]

logger = logging.getLogger(__name__)


class MultitenantBackgroundJobMixin:
    """Mixin that adds automatic tenant filtering to background job repository operations.

    This mixin intercepts all job repository methods to inject tenant_id
    filtering. It should be used via MRO composition:

        class MyJobRepo(MultitenantBackgroundJobMixin, SQLAlchemyBackgroundJobRepository):
            pass

    Key behaviors:
    - **add()**: Injects tenant_id into job's dedicated field and metadata
    - **get()**: Returns None for cross-tenant access (silent denial)
    - **get_stale_jobs()**: Passes tenant spec for DB-level filtering
    - **find_by_status()**: Passes tenant spec for DB-level filtering
    - **count_by_status()**: Passes tenant spec for DB-level filtering
    - **purge_completed()**: Passes tenant spec for DB-level filtering

    The tenant ID is stored in both the job's dedicated ``tenant_id``
    field (for DB-level specification filtering) and the ``metadata``
    dict (for backward compatibility).

    Attributes:
        _tenant_metadata_key: The metadata key for tenant ID (default: "tenant_id")
    """

    # These can be overridden in subclasses
    _tenant_metadata_key: str = "tenant_id"

    def _get_tenant_metadata_key(self) -> str:
        """Get the tenant metadata key."""
        return getattr(self, "_tenant_metadata_key", "tenant_id")

    def _require_tenant_context(self) -> str:
        """Require and return the current tenant ID.

        Raises:
            TenantContextMissingError: If no tenant context is set.
        """
        tenant = get_current_tenant_or_none()
        if tenant is None and not is_system_tenant():
            raise TenantContextMissingError(
                "Tenant context required for background job operation. "
                "Ensure TenantMiddleware is configured or use @system_operation."
            )
        return tenant or "__system__"

    def _build_tenant_specification(self, tenant_id: str) -> Any:
        """Build a tenant specification for job filtering.

        Uses ``AttributeSpecification`` targeting the dedicated ``tenant_id``
        column for DB-level WHERE clause filtering (not in-memory metadata).
        """
        try:
            from cqrs_ddd_specifications import AttributeSpecification
            from cqrs_ddd_specifications.operators import SpecificationOperator
            from cqrs_ddd_specifications.operators_memory import build_default_registry

            return AttributeSpecification(
                attr="tenant_id",
                op=SpecificationOperator.EQ,
                val=tenant_id,
                registry=build_default_registry(),
            )
        except ImportError:
            logger.warning(
                "cqrs-ddd-specifications not installed, using dict filter fallback",
                extra={"tenant_id": tenant_id},
            )
            return {
                "attr": "tenant_id",
                "op": "eq",
                "val": tenant_id,
            }

    def _get_tenant_id_from_job(self, job: BaseBackgroundJob) -> str | None:
        """Extract tenant_id from a job.

        Resolution order:
        1. Dedicated ``tenant_id`` attribute (DB column)
        2. Metadata dict fallback (backward compatibility)
        """
        tenant_key = self._get_tenant_metadata_key()
        # 1. Dedicated attribute
        val = getattr(job, "tenant_id", None)
        if val is not None:
            return val  # type: ignore[no-any-return]
        # 2. Metadata fallback
        return job.metadata.get(tenant_key)

    def _inject_tenant_to_job(self, job: BaseBackgroundJob, tenant_id: str) -> None:
        """Inject tenant_id into job.

        Sets BOTH the dedicated ``tenant_id`` attribute (for DB-level spec
        filtering) and the metadata key (for backward compatibility).

        Raises:
            CrossTenantAccessError: If job belongs to different tenant.
        """
        tenant_key = self._get_tenant_metadata_key()
        current_tenant = self._get_tenant_id_from_job(job)

        if current_tenant is not None and current_tenant != tenant_id:
            raise CrossTenantAccessError(
                current_tenant=tenant_id,
                target_tenant=current_tenant,
                resource_type="BaseBackgroundJob",
                resource_id=job.id,
            )

        # Always ensure dedicated attribute is set
        if getattr(job, "tenant_id", None) is None:
            object.__setattr__(job, "tenant_id", tenant_id)

        # Always ensure metadata has tenant for backward compat
        if tenant_key not in job.metadata:
            metadata = dict(job.metadata)
            metadata[tenant_key] = tenant_id
            object.__setattr__(job, "metadata", metadata)

    # ── IRepository Protocol Methods ─────────────────────────────────────

    async def add(self: Any, job: BaseBackgroundJob) -> None:
        """Add a new job with automatic tenant injection."""
        if is_system_tenant():
            return await super().add(job)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        self._inject_tenant_to_job(job, tenant_id)
        await super().add(job)  # type: ignore[misc]

    async def get(self: Any, job_id: str) -> BaseBackgroundJob | None:
        """Get a job by ID with tenant filtering (silent denial)."""
        if is_system_tenant():
            return await super().get(job_id)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        job = await super().get(job_id)  # type: ignore[misc]

        if job is None:
            return None

        job_tenant = self._get_tenant_id_from_job(job)
        if job_tenant is not None and job_tenant != tenant_id:
            logger.debug(
                "Cross-tenant job access attempt: job tenant=%s, context tenant=%s",
                job_tenant,
                tenant_id,
            )
            return None

        return job  # type: ignore[no-any-return]

    async def update(self: Any, job: BaseBackgroundJob) -> None:
        """Update a job with tenant validation."""
        if is_system_tenant():
            return await super().update(job)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        job_tenant = self._get_tenant_id_from_job(job)

        if job_tenant is not None and job_tenant != tenant_id:
            raise CrossTenantAccessError(
                current_tenant=tenant_id,
                target_tenant=job_tenant,
                resource_type="BaseBackgroundJob",
                resource_id=job.id,
            )

        await super().update(job)  # type: ignore[misc]

    async def delete(self: Any, job: BaseBackgroundJob) -> None:
        """Delete a job with tenant validation."""
        if is_system_tenant():
            return await super().delete(job)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        job_tenant = self._get_tenant_id_from_job(job)

        if job_tenant is not None and job_tenant != tenant_id:
            raise CrossTenantAccessError(
                current_tenant=tenant_id,
                target_tenant=job_tenant,
                resource_type="BaseBackgroundJob",
                resource_id=job.id,
            )

        await super().delete(job)  # type: ignore[misc]

    async def list_all(
        self: Any,
        entity_ids: list[str] | None = None,
        uow: UnitOfWork | None = None,
        *,
        specification: Any | None = None,
    ) -> list[BaseBackgroundJob]:
        """List all jobs with spec-based tenant filtering."""
        if is_system_tenant():
            return await super().list_all(  # type: ignore[misc, no-any-return]
                entity_ids, uow, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().list_all(  # type: ignore[misc, no-any-return]
            entity_ids, uow, specification=combined
        )

    async def search(
        self: Any,
        criteria: Any,
        uow: UnitOfWork | None = None,
    ) -> SearchResult[BaseBackgroundJob]:
        """Search jobs with automatic tenant filtering via specification."""
        if is_system_tenant():
            return await super().search(criteria, uow)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)

        if criteria is not None and hasattr(criteria, "__and__"):
            combined = tenant_spec & criteria
        else:
            combined = tenant_spec

        return await super().search(combined, uow)  # type: ignore[misc, no-any-return]

    # ── IBackgroundJobRepository Protocol Methods ────────────────────────

    async def get_stale_jobs(
        self: Any,
        timeout_seconds: int | None = None,
        uow: UnitOfWork | None = None,
        *,
        specification: Any | None = None,
    ) -> list[BaseBackgroundJob]:
        """Fetch stale RUNNING jobs via specification-based tenant filtering.

        System tenant returns ALL stale jobs (e.g. recovery workers).
        """
        if is_system_tenant():
            return await super().get_stale_jobs(  # type: ignore[misc, no-any-return]
                timeout_seconds, uow, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().get_stale_jobs(  # type: ignore[misc, no-any-return]
            timeout_seconds, uow, specification=combined
        )

    async def find_by_status(
        self: Any,
        statuses: list[BackgroundJobStatus],
        limit: int = 50,
        offset: int = 0,
        uow: UnitOfWork | None = None,
        *,
        specification: Any | None = None,
    ) -> list[BaseBackgroundJob]:
        """Return jobs matching statuses via spec-based tenant filtering."""
        if is_system_tenant():
            return await super().find_by_status(  # type: ignore[misc, no-any-return]
                statuses,
                limit=limit,
                offset=offset,
                uow=uow,
                specification=specification,
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().find_by_status(  # type: ignore[misc, no-any-return]
            statuses,
            limit=limit,
            offset=offset,
            uow=uow,
            specification=combined,
        )

    async def count_by_status(
        self: Any,
        uow: UnitOfWork | None = None,
        *,
        specification: Any | None = None,
    ) -> dict[str, int]:
        """Return status → count mapping via spec-based tenant filtering."""
        if is_system_tenant():
            return await super().count_by_status(  # type: ignore[misc, no-any-return]
                uow, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().count_by_status(  # type: ignore[misc, no-any-return]
            uow, specification=combined
        )

    async def purge_completed(
        self: Any,
        before: datetime,
        uow: UnitOfWork | None = None,
        *,
        specification: Any | None = None,
    ) -> int:
        """Delete COMPLETED/CANCELLED jobs via spec-based tenant filtering."""
        if is_system_tenant():
            return await super().purge_completed(  # type: ignore[misc, no-any-return]
                before, uow, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = tenant_spec & specification if specification else tenant_spec
        return await super().purge_completed(  # type: ignore[misc, no-any-return]
            before, uow, specification=combined
        )

    async def is_cancellation_requested(
        self: Any,
        job_id: str,
        uow: UnitOfWork | None = None,
    ) -> bool:
        """Check whether the job is CANCELLED, with tenant validation."""
        if is_system_tenant():
            return await super().is_cancellation_requested(job_id, uow)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        job = await super().get(job_id)  # type: ignore[misc]

        if job is None:
            return False

        job_tenant = self._get_tenant_id_from_job(job)
        if job_tenant is not None and job_tenant != tenant_id:
            return False

        from cqrs_ddd_advanced_core.background_jobs.entity import BackgroundJobStatus

        return job.status == BackgroundJobStatus.CANCELLED  # type: ignore[no-any-return]
