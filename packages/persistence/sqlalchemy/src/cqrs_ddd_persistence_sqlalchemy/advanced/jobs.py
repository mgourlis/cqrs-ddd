"""
SQLAlchemy implementation of Background Job persistence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, func, select

from cqrs_ddd_advanced_core.background_jobs.entity import (
    BackgroundJobStatus as DomainJobStatus,
)
from cqrs_ddd_advanced_core.background_jobs.entity import BaseBackgroundJob
from cqrs_ddd_advanced_core.ports.background_jobs import IBackgroundJobRepository

from ..core.repository import SQLAlchemyRepository, UnitOfWorkFactory
from .models import BackgroundJobModel, JobStatus

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from ..core.uow import SQLAlchemyUnitOfWork

_TERMINAL_STATUSES = (JobStatus.COMPLETED, JobStatus.CANCELLED)


class SQLAlchemyBackgroundJobRepository(
    SQLAlchemyRepository[BaseBackgroundJob, str], IBackgroundJobRepository
):
    """
    SQLAlchemy-backed persistence for background jobs.
    Inherits from the generic SQLAlchemyRepository for standard CRUD,
    and implements IBackgroundJobRepository for specialized job queries.
    """

    def __init__(
        self,
        job_cls: type[BaseBackgroundJob] = BaseBackgroundJob,
        uow_factory: UnitOfWorkFactory | None = None,
        stale_job_timeout_seconds: int = 3600,
    ) -> None:
        super().__init__(job_cls, BackgroundJobModel, uow_factory=uow_factory)
        self._job_domain_cls = job_cls
        self.stale_job_timeout_seconds = stale_job_timeout_seconds

    def to_model(self, entity: BaseBackgroundJob) -> BackgroundJobModel:
        """
        Custom mapping to handle job-specific fields.
        """
        model = super().to_model(entity)
        # Handle metadata mapping (domain uses 'metadata', model uses 'job_metadata')
        model.job_metadata = entity.metadata
        return cast("BackgroundJobModel", model)

    def from_model(self, model: BackgroundJobModel) -> BaseBackgroundJob:
        """
        Convert SQLAlchemy model back to domain BaseBackgroundJob.
        """
        data = model.state.copy() if hasattr(model, "state") and model.state else {}

        # Ensure critical fields from columns override state
        # snapshot or are used for reconstruction
        data["id"] = model.id
        data["job_type"] = model.job_type
        data["status"] = DomainJobStatus(model.status.value)
        data["_version"] = model.version
        data["total_items"] = model.total_items
        data["processed_items"] = model.processed_items
        data["result_data"] = model.result_data
        data["error_message"] = model.error_message
        data["broker_message_id"] = model.broker_message_id
        data["retry_count"] = model.retry_count
        data["max_retries"] = model.max_retries
        data["created_at"] = model.created_at
        data["updated_at"] = model.updated_at
        data["metadata"] = model.job_metadata
        data["correlation_id"] = model.correlation_id

        return self._job_domain_cls(**data)

    async def get_stale_jobs(
        self,
        timeout_seconds: int | None = None,
        uow: UnitOfWork | None = None,
    ) -> list[BaseBackgroundJob]:
        """Fetch RUNNING jobs that have exceeded their timeout.

        Args:
            timeout_seconds: Override the default timeout.
                If None, uses ``self.stale_job_timeout_seconds``.
            uow: Optional UnitOfWork to use.

        Returns:
            List of stale jobs.
        """
        active_uow = self._get_active_uow(cast("SQLAlchemyUnitOfWork | None", uow))
        if not active_uow:
            raise ValueError("No active UnitOfWork or factory found.")

        seconds = timeout_seconds or self.stale_job_timeout_seconds
        threshold = datetime.now(timezone.utc) - timedelta(seconds=seconds)

        stmt = select(BackgroundJobModel).where(
            BackgroundJobModel.status == JobStatus.RUNNING,
            BackgroundJobModel.updated_at < threshold,
        )
        result = await active_uow.session.execute(stmt)
        return [self.from_model(m) for m in result.scalars().all()]

    async def find_by_status(
        self,
        statuses: list[DomainJobStatus],
        limit: int = 50,
        offset: int = 0,
        uow: UnitOfWork | None = None,
    ) -> list[BaseBackgroundJob]:
        """Return jobs matching any of the given statuses, ordered by updated_at desc.

        Args:
            statuses: Domain status values to filter by.
            limit: Maximum number of results.
            offset: Number of results to skip.
            uow: Optional UnitOfWork to use.
        """
        active_uow = self._get_active_uow(cast("SQLAlchemyUnitOfWork | None", uow))
        if not active_uow:
            raise ValueError("No active UnitOfWork or factory found.")

        model_statuses = [JobStatus(s.value) for s in statuses]
        stmt = (
            select(BackgroundJobModel)
            .where(BackgroundJobModel.status.in_(model_statuses))
            .order_by(BackgroundJobModel.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await active_uow.session.execute(stmt)
        return [self.from_model(m) for m in result.scalars().all()]

    async def count_by_status(
        self,
        uow: UnitOfWork | None = None,
    ) -> dict[str, int]:
        """Return a mapping of status value → job count (omits zero-count statuses).

        Args:
            uow: Optional UnitOfWork to use.
        """
        active_uow = self._get_active_uow(cast("SQLAlchemyUnitOfWork | None", uow))
        if not active_uow:
            raise ValueError("No active UnitOfWork or factory found.")

        stmt = select(
            BackgroundJobModel.status,
            func.count().label("cnt"),
        ).group_by(BackgroundJobModel.status)
        result = await active_uow.session.execute(stmt)
        return {row.status.value: row.cnt for row in result.all()}

    async def is_cancellation_requested(
        self,
        job_id: str,
        uow: UnitOfWork | None = None,
    ) -> bool:
        """Check if the job's stored status is CANCELLED (single-column query).

        Args:
            job_id: ID of the job to check.
            uow: Optional UnitOfWork to use.
        """
        active_uow = self._get_active_uow(cast("SQLAlchemyUnitOfWork | None", uow))
        if not active_uow:
            raise ValueError("No active UnitOfWork or factory found.")

        stmt = select(BackgroundJobModel.status).where(BackgroundJobModel.id == job_id)
        status = await active_uow.session.scalar(stmt)
        return status == JobStatus.CANCELLED

    async def purge_completed(
        self,
        before: datetime,
        uow: UnitOfWork | None = None,
    ) -> int:
        """Delete COMPLETED and CANCELLED jobs with updated_at older than before.

        Args:
            before: UTC datetime threshold.
            uow: Optional UnitOfWork to use.

        Returns:
            Number of jobs deleted.
        """
        active_uow = self._get_active_uow(cast("SQLAlchemyUnitOfWork | None", uow))
        if not active_uow:
            raise ValueError("No active UnitOfWork or factory found.")

        stmt = delete(BackgroundJobModel).where(
            BackgroundJobModel.status.in_(_TERMINAL_STATUSES),
            BackgroundJobModel.updated_at < before,
        )
        result = await active_uow.session.execute(stmt)
        # CursorResult.rowcount; Result type stubs may not expose it
        n: int = int(getattr(result, "rowcount", 0) or 0)
        return n
