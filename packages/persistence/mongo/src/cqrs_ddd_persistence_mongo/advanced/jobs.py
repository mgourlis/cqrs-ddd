"""MongoDB implementation of Background Job persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_advanced_core.background_jobs.entity import (
    BackgroundJobStatus as DomainJobStatus,
)
from cqrs_ddd_advanced_core.background_jobs.entity import BaseBackgroundJob
from cqrs_ddd_advanced_core.ports.background_jobs import IBackgroundJobRepository

from ..core.repository import MongoRepository
from ..query_builder import MongoQueryBuilder

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from ..connection import MongoConnectionManager


class MongoBackgroundJobRepository(
    MongoRepository[BaseBackgroundJob], IBackgroundJobRepository
):
    """
    MongoDB-backed persistence for background jobs.
    Inherits from the generic MongoRepository for standard CRUD,
    and implements IBackgroundJobRepository for specialized job queries.
    """

    def __init__(
        self,
        connection: MongoConnectionManager,
        collection: str = "background_jobs",
        job_cls: type[BaseBackgroundJob] = BaseBackgroundJob,
        database: str | None = None,
        stale_job_timeout_seconds: int = 3600,
    ) -> None:
        super().__init__(
            connection=connection,
            collection=collection,
            model_cls=job_cls,
            database=database,
        )
        self.stale_job_timeout_seconds = stale_job_timeout_seconds

    def _merge_spec(
        self, query: dict[str, Any], specification: ISpecification[Any] | None
    ) -> dict[str, Any]:
        """Merge a specification filter into a MongoDB query dict."""
        if specification is None:
            return query
        builder = MongoQueryBuilder()
        spec_filter = builder.build_match(specification)
        if not spec_filter:
            return query
        if query:
            return {"$and": [query, spec_filter]}
        return spec_filter

    async def get_stale_jobs(
        self,
        timeout_seconds: int | None = None,
        uow: UnitOfWork | None = None,  # noqa: ARG002
        *,
        specification: ISpecification[Any] | None = None,
    ) -> list[BaseBackgroundJob]:
        """Fetch RUNNING jobs that have exceeded their timeout."""
        timeout = timeout_seconds or self.stale_job_timeout_seconds
        threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout)

        base_query = {
            "status": DomainJobStatus.RUNNING.value,
            "updated_at": {"$lt": threshold},
        }
        query = self._merge_spec(base_query, specification)

        cursor = self._collection().find(query)

        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results

    async def find_by_status(
        self,
        statuses: list[DomainJobStatus],
        limit: int = 50,
        offset: int = 0,
        uow: UnitOfWork | None = None,  # noqa: ARG002
        *,
        specification: ISpecification[Any] | None = None,
    ) -> list[BaseBackgroundJob]:
        """Find jobs by status."""
        status_values = [s.value for s in statuses]
        base_query: dict[str, Any] = {
            "status": {"$in": status_values},
        }
        query = self._merge_spec(base_query, specification)

        cursor = self._collection().find(query).skip(offset).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results

    async def claim_next_job(
        self,
        worker_id: str,
        _timeout_seconds: int = 300,
        _uow: UnitOfWork | None = None,
    ) -> BaseBackgroundJob | None:
        """
        Atomically claim next pending job using findAndModify.

        This is a NoSQL-native pattern that eliminates race conditions
        without requiring database-level locks.

        Args:
            worker_id: Unique identifier for the worker claiming the job
            timeout_seconds: Job timeout (will be marked as stale after this)
            uow: Optional UnitOfWork (not used for atomic claim)

        Returns:
            Claimed job or None if no pending jobs
        """
        now = datetime.now(timezone.utc)

        # Atomic findAndModify operation
        result = await self._collection().find_one_and_update(
            {
                "status": DomainJobStatus.PENDING.value,
                "$or": [
                    {"scheduled_at": {"$exists": False}},
                    {"scheduled_at": {"$lte": now}},
                ],
            },
            {
                "$set": {
                    "status": DomainJobStatus.RUNNING.value,
                    "started_at": now,
                    "worker_id": worker_id,
                    "updated_at": now,
                },
                "$inc": {"retry_count": 1},
            },
            sort=[("created_at", 1)],
            return_document=True,  # Return updated document
        )

        return self._mapper.from_doc(result) if result else None

    async def mark_for_retry(
        self,
        job_id: str,
        error_message: str | None = None,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> bool:
        """
        Mark a failed job for retry.

        Args:
            job_id: Job ID to mark for retry
            error_message: Optional error message
            uow: Optional UnitOfWork

        Returns:
            True if job was marked for retry, False if max retries exceeded
        """
        now = datetime.now(timezone.utc)

        # Get current job
        job = await self.get(job_id, uow=uow)
        if not job:
            return False

        # Check if max retries exceeded
        if job.retry_count >= job.max_retries:
            # Mark as failed permanently
            await self._collection().update_one(
                {"_id": job_id},
                {
                    "$set": {
                        "status": DomainJobStatus.FAILED.value,
                        "error_message": error_message or "Max retries exceeded",
                        "updated_at": now,
                    }
                },
            )
            return False

        # Mark for retry
        await self._collection().update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": DomainJobStatus.PENDING.value,
                    "error_message": error_message,
                    "updated_at": now,
                }
            },
        )
        return True

    async def mark_completed(
        self,
        job_id: str,
        result_data: dict[str, Any] | None = None,
        _uow: UnitOfWork | None = None,
    ) -> None:
        """Mark a job as completed."""
        now = datetime.now(timezone.utc)

        update_doc = {
            "status": DomainJobStatus.COMPLETED.value,
            "completed_at": now,
            "updated_at": now,
        }

        if result_data:
            update_doc["result_data"] = result_data

        await self._collection().update_one(
            {"_id": job_id},
            {"$set": update_doc},
        )

    async def count_by_status(
        self,
        uow: UnitOfWork | None = None,  # noqa: ARG002
        *,
        specification: ISpecification[Any] | None = None,
    ) -> dict[str, int]:
        """Return a mapping of status value → job count across all statuses."""
        coll = self._collection()
        base_query: dict[str, Any] = {}
        query = self._merge_spec(base_query, specification)

        pipeline: list[dict[str, Any]] = []
        if query:
            pipeline.append({"$match": query})
        pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})

        result: dict[str, int] = {}
        async for doc in coll.aggregate(pipeline):
            result[doc["_id"]] = doc["count"]
        return result

    async def purge_completed(
        self,
        before: datetime,
        uow: UnitOfWork | None = None,  # noqa: ARG002
        *,
        specification: ISpecification[Any] | None = None,
    ) -> int:
        """Delete COMPLETED and CANCELLED jobs whose updated_at precedes ``before``."""
        coll = self._collection()
        base_query: dict[str, Any] = {
            "status": {
                "$in": [
                    DomainJobStatus.COMPLETED.value,
                    DomainJobStatus.CANCELLED.value,
                ]
            },
            "updated_at": {"$lt": before},
        }
        query = self._merge_spec(base_query, specification)

        result = await coll.delete_many(query)
        return int(result.deleted_count)

    async def is_cancellation_requested(
        self,
        job_id: str,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> bool:
        """Check whether the job's persisted status is CANCELLED."""
        coll = self._collection()
        doc = await coll.find_one(
            {"_id": job_id},
            projection={"status": 1},
        )
        if doc is None:
            return False
        return bool(doc.get("status") == DomainJobStatus.CANCELLED.value)
