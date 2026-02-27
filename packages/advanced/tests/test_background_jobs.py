"""Tests for the Background Jobs package."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from cqrs_ddd_advanced_core.adapters.asyncio_task_registry import (
    AsyncioJobTaskRegistry,
)
from cqrs_ddd_advanced_core.adapters.memory import InMemoryBackgroundJobRepository
from cqrs_ddd_advanced_core.background_jobs import (
    BackgroundJobAdminService,
    BackgroundJobEventHandler,
    BackgroundJobService,
    BackgroundJobStatus,
    BaseBackgroundJob,
    JobCancelled,
    JobCompleted,
    JobCreated,
    JobFailed,
    JobRetried,
    JobStarted,
    JobSweeperWorker,
)
from cqrs_ddd_advanced_core.exceptions import (
    CancellationRequestedError,
    JobStateError,
)
from cqrs_ddd_core.domain.events import DomainEvent

# ============================================================================
# Tests: BaseBackgroundJob Entity
# ============================================================================


class TestBaseBackgroundJobEntity:
    """Test the BaseBackgroundJob entity and state transitions."""

    def test_create_emits_job_created_event(self) -> None:
        """Factory method should emit JobCreated."""
        job = BaseBackgroundJob.create(
            job_type="EmailTask",
            total_items=100,
            correlation_id="corr-123",
        )

        assert job.status == BackgroundJobStatus.PENDING
        assert job.job_type == "EmailTask"
        assert job.total_items == 100

        events = job.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], JobCreated)
        assert events[0].job_type == "EmailTask"

    def test_start_processing_pending_to_running(self) -> None:
        """PENDING → RUNNING should emit JobStarted."""
        job = BaseBackgroundJob.create(job_type="Task")

        job.start_processing()

        assert job.status == BackgroundJobStatus.RUNNING
        events = job.collect_events()
        assert any(isinstance(e, JobStarted) for e in events)

    def test_start_processing_invalid_state_raises(self) -> None:
        """Cannot start from COMPLETED."""
        job = BaseBackgroundJob(job_type="Task", status=BackgroundJobStatus.COMPLETED)

        with pytest.raises(JobStateError, match="Cannot start"):
            job.start_processing()

    def test_complete_running_to_completed(self) -> None:
        """RUNNING → COMPLETED should emit JobCompleted."""
        job = BaseBackgroundJob.create(job_type="Task")
        job.start_processing()
        job.collect_events()

        job.complete(result_data={"count": 42})

        assert job.status == BackgroundJobStatus.COMPLETED
        assert job.result_data == {"count": 42}
        events = job.collect_events()
        assert any(isinstance(e, JobCompleted) for e in events)

    def test_fail_running_to_failed(self) -> None:
        """RUNNING → FAILED should emit JobFailed."""
        job = BaseBackgroundJob.create(job_type="Task")
        job.start_processing()
        job.collect_events()

        job.fail("Network timeout")

        assert job.status == BackgroundJobStatus.FAILED
        assert job.error_message == "Network timeout"
        events = job.collect_events()
        assert any(isinstance(e, JobFailed) for e in events)

    def test_retry_failed_to_running(self) -> None:
        """FAILED → RUNNING should emit JobRetried."""
        job = BaseBackgroundJob.create(job_type="Task", max_retries=3)
        job.fail("Initial error")
        job.collect_events()

        job.retry()

        assert job.status == BackgroundJobStatus.RUNNING
        assert job.retry_count == 1
        assert job.error_message is None
        events = job.collect_events()
        assert any(isinstance(e, JobRetried) for e in events)

    def test_retry_exceeding_max_raises(self) -> None:
        """Cannot retry beyond max_retries."""
        job = BaseBackgroundJob.create(job_type="Task", max_retries=2)

        # First retry cycle
        job.fail("Error 1")
        job.retry()

        # Second retry cycle
        job.fail("Error 2")
        job.retry()

        # Third attempt should fail (exceeded max)
        job.fail("Error 3")
        with pytest.raises(JobStateError, match="Max retries"):
            job.retry()

    def test_cancel_pending_to_cancelled(self) -> None:
        """PENDING → CANCELLED should emit JobCancelled."""
        job = BaseBackgroundJob.create(job_type="Task")
        job.collect_events()

        job.cancel()

        assert job.status == BackgroundJobStatus.CANCELLED
        assert job.error_message == "Cancelled by user"
        events = job.collect_events()
        assert any(isinstance(e, JobCancelled) for e in events)

    def test_cancel_completed_raises(self) -> None:
        """Cannot cancel already-completed job."""
        job = BaseBackgroundJob.create(job_type="Task")
        job.status = BackgroundJobStatus.COMPLETED

        with pytest.raises(JobStateError, match="Cannot cancel"):
            job.cancel()

    def test_update_progress_capped_at_total(self) -> None:
        """Updating progress while RUNNING."""
        job = BaseBackgroundJob.create(job_type="Task", total_items=100)
        job.start_processing()

        job.update_progress(50)

        assert job.processed_items == 50

    def test_version_increments_on_transitions(self) -> None:
        """Every domain transition increments version."""
        job = BaseBackgroundJob.create(job_type="Task")
        v0 = job.version

        job.start_processing()

        # Version is persistence-managed; domain transitions do not change it until save
        assert job.version == v0


# ============================================================================
# Tests: BackgroundJobService
# ============================================================================


class TestBackgroundJobService:
    """Test the BackgroundJobService."""

    @pytest.mark.asyncio
    async def test_schedule_persists_job(self) -> None:
        """schedule() should persist the new job."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)
        job = BaseBackgroundJob.create(job_type="EmailTask", total_items=10)

        result = await service.schedule(job)

        assert result.id == job.id
        stored = await persistence.get(job.id)
        assert stored.id == job.id

    @pytest.mark.asyncio
    async def test_get_retrieves_job(self) -> None:
        """get() should retrieve the job."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)
        job = BaseBackgroundJob.create(job_type="Task")
        await persistence.add(job)

        result = await service.get(job.id)

        assert result is not None
        assert result.id == job.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self) -> None:
        """get() for missing job returns None."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        result = await service.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_transitions_to_cancelled(self) -> None:
        """cancel() transitions job to CANCELLED."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)
        job = BaseBackgroundJob.create(job_type="Task")
        await persistence.add(job)

        result = await service.cancel(job.id)

        assert result is not None
        assert result.status == BackgroundJobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_retry_transitions_to_running(self) -> None:
        """retry() transitions FAILED to RUNNING."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)
        job = BaseBackgroundJob.create(job_type="Task", max_retries=3)
        job.fail("Initial error")
        await persistence.add(job)

        result = await service.retry(job.id)

        assert result is not None
        assert result.status == BackgroundJobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_process_stale_jobs_marks_timed_out_as_failed(self) -> None:
        """process_stale_jobs() should mark RUNNING jobs past timeout as FAILED."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        # Create a stale job (RUNNING, updated >1s ago)
        job = BaseBackgroundJob.create(job_type="SlowTask", timeout_seconds=1)
        job.start_processing()
        # Backdate it
        stale_updated = datetime.now(timezone.utc) - timedelta(seconds=10)
        job.updated_at = stale_updated
        await persistence.add(job)

        swept = await service.process_stale_jobs(timeout_seconds=1)

        assert swept == 1
        stored = await persistence.get(job.id)
        assert stored.status == BackgroundJobStatus.FAILED
        assert "timed out" in stored.error_message.lower()

    @pytest.mark.asyncio
    async def test_process_stale_jobs_skips_completed(self) -> None:
        """process_stale_jobs() should skip COMPLETED jobs."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        job = BaseBackgroundJob.create(job_type="Task")
        job.status = BackgroundJobStatus.COMPLETED
        job.updated_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await persistence.add(job)

        swept = await service.process_stale_jobs()

        assert swept == 0
        stored = await persistence.get(job.id)
        assert stored.status == BackgroundJobStatus.COMPLETED


# ============================================================================
# Tests: JobSweeperWorker
# ============================================================================


class TestJobSweeperWorker:
    """Test the JobSweeperWorker background process."""

    @pytest.mark.asyncio
    async def test_worker_initializes_and_stops(self) -> None:
        """Worker should start and stop cleanly."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)
        worker = JobSweeperWorker(service, poll_interval=0.1)

        await worker.start()
        assert worker._running
        await asyncio.sleep(0.2)
        await worker.stop()
        assert not worker._running

    @pytest.mark.asyncio
    async def test_worker_run_once_sweeps_stale(self) -> None:
        """run_once() should perform a single sweep."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)
        worker = JobSweeperWorker(service, timeout_seconds=1)

        # Add stale job
        job = BaseBackgroundJob.create(job_type="Task")
        job.start_processing()
        job.updated_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await persistence.add(job)

        count = await worker.run_once()

        assert count == 1
        stored = await persistence.get(job.id)
        assert stored.status == BackgroundJobStatus.FAILED


# ============================================================================
# Tests: BackgroundJobEventHandler (abstract)
# ============================================================================


class DummyJobEventHandler(BackgroundJobEventHandler[DomainEvent]):
    """Concrete test implementation of BackgroundJobEventHandler."""

    async def execute(
        self, event: DomainEvent, job: BaseBackgroundJob
    ) -> dict[str, Any] | None:
        return {"processed": True}


class TestBackgroundJobEventHandler:
    """Test the BackgroundJobEventHandler base."""

    @pytest.mark.asyncio
    async def test_handler_loads_job_and_processes(self) -> None:
        """Handler should load job, process, and mark complete."""
        persistence = InMemoryBackgroundJobRepository()
        handler = DummyJobEventHandler(persistence)

        job = BaseBackgroundJob.create(job_type="EmailTask")
        job.correlation_id = job.id
        await persistence.add(job)

        event = JobCreated(
            job_type="Task",
            correlation_id=job.id,
        )

        await handler.handle(event)

        stored = await persistence.get(job.id)
        assert stored.status == BackgroundJobStatus.COMPLETED
        assert stored.result_data == {"processed": True}

    @pytest.mark.asyncio
    async def test_handler_missing_correlation_id_logs_warning(
        self, caplog: Any
    ) -> None:
        """Handler should warn if event lacks correlation_id."""
        persistence = InMemoryBackgroundJobRepository()
        handler = DummyJobEventHandler(persistence)

        event = JobCreated(job_type="Task")
        # No correlation_id set

        await handler.handle(event)

        assert "correlation_id" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_handler_missing_job_logs_warning(self, caplog: Any) -> None:
        """Handler should warn if job not found."""
        persistence = InMemoryBackgroundJobRepository()
        handler = DummyJobEventHandler(persistence)

        event = JobCreated(
            job_type="Task",
            correlation_id="missing",
        )

        await handler.handle(event)

        assert "not found" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_handler_failure_calls_on_failure_hook(self) -> None:
        """Handler should call on_failure hook if execute raises."""

        class FailingHandler(DummyJobEventHandler):
            def __init__(self, persistence: Any) -> None:
                super().__init__(persistence)
                self.failure_hook_called = False

            async def execute(
                self, event: DomainEvent, job: BaseBackgroundJob
            ) -> dict[str, Any] | None:
                raise ValueError("Intentional error")

            async def on_failure(
                self, event: DomainEvent, job: BaseBackgroundJob, error: Exception
            ) -> None:
                self.failure_hook_called = True

        persistence = InMemoryBackgroundJobRepository()
        handler = FailingHandler(persistence)

        job = BaseBackgroundJob.create(job_type="Task")
        job.correlation_id = job.id
        await persistence.add(job)

        event = JobCreated(
            job_type="Task",
            correlation_id=job.id,
        )

        with pytest.raises(ValueError, match="Intentional error"):
            await handler.handle(event)

        assert handler.failure_hook_called

        stored = await persistence.get(job.id)
        assert stored.status == BackgroundJobStatus.FAILED


# ============================================================================
# Tests: InMemoryBackgroundJobRepository
# ============================================================================


class TestInMemoryBackgroundJobRepository:
    """Test the in-memory repository implementation."""

    @pytest.mark.asyncio
    async def test_add_and_get(self) -> None:
        """add() and get() should round-trip."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="Task")

        await persistence.add(job)
        stored = await persistence.get(job.id)

        assert stored is not None
        assert stored.id == job.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self) -> None:
        """get() should return None for missing job."""
        persistence = InMemoryBackgroundJobRepository()

        result = await persistence.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_all_jobs(self) -> None:
        """list() should return all stored jobs."""
        persistence = InMemoryBackgroundJobRepository()
        job1 = BaseBackgroundJob.create(job_type="Task1")
        job2 = BaseBackgroundJob.create(job_type="Task2")
        await persistence.add(job1)
        await persistence.add(job2)

        result = await persistence.list_all()

        assert len(result) == 2
        ids = {j.id for j in result}
        assert ids == {job1.id, job2.id}

    @pytest.mark.asyncio
    async def test_get_stale_jobs_detects_timeout(self) -> None:
        """get_stale_jobs() should detect jobs past timeout."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="Task", timeout_seconds=1)
        job.status = BackgroundJobStatus.RUNNING
        job.updated_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        await persistence.add(job)

        stale = await persistence.get_stale_jobs(timeout_seconds=1)

        assert len(stale) == 1
        assert stale[0].id == job.id

    @pytest.mark.asyncio
    async def test_delete_removes_job(self) -> None:
        """delete() should remove a job."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="Task")
        await persistence.add(job)

        await persistence.delete(job.id)

        result = await persistence.get(job.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_is_cancellation_requested_true_when_cancelled(self) -> None:
        """is_cancellation_requested() returns True when job is CANCELLED."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="Task")
        job.cancel()
        await persistence.add(job)

        result = await persistence.is_cancellation_requested(job.id)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_cancellation_requested_false_when_running(self) -> None:
        """is_cancellation_requested() returns False when job is RUNNING."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="Task")
        job.start_processing()
        await persistence.add(job)

        result = await persistence.is_cancellation_requested(job.id)

        assert result is False

    @pytest.mark.asyncio
    async def test_is_cancellation_requested_false_for_missing_job(self) -> None:
        """is_cancellation_requested() returns False for missing job."""
        persistence = InMemoryBackgroundJobRepository()

        result = await persistence.is_cancellation_requested("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_find_by_status_returns_paginated_matches(self) -> None:
        """find_by_status() returns jobs matching statuses, ordered by updated_at desc."""
        persistence = InMemoryBackgroundJobRepository()
        job1 = BaseBackgroundJob.create(job_type="A")
        job1.status = BackgroundJobStatus.FAILED
        await persistence.add(job1)
        job2 = BaseBackgroundJob.create(job_type="B")
        job2.status = BackgroundJobStatus.FAILED
        await persistence.add(job2)
        job3 = BaseBackgroundJob.create(job_type="C")
        job3.status = BackgroundJobStatus.PENDING
        await persistence.add(job3)

        result = await persistence.find_by_status(
            [BackgroundJobStatus.FAILED], limit=10, offset=0
        )

        assert len(result) == 2
        assert {j.id for j in result} == {job1.id, job2.id}

    @pytest.mark.asyncio
    async def test_count_by_status_returns_counts_per_status(self) -> None:
        """count_by_status() returns mapping of status value to count."""
        persistence = InMemoryBackgroundJobRepository()
        for _ in range(2):
            j = BaseBackgroundJob.create(job_type="T")
            j.status = BackgroundJobStatus.PENDING
            await persistence.add(j)
        j3 = BaseBackgroundJob.create(job_type="T")
        j3.status = BackgroundJobStatus.RUNNING
        await persistence.add(j3)

        counts = await persistence.count_by_status()

        assert counts.get("PENDING") == 2
        assert counts.get("RUNNING") == 1

    @pytest.mark.asyncio
    async def test_purge_completed_deletes_old_terminal_jobs(self) -> None:
        """purge_completed() deletes COMPLETED/CANCELLED jobs older than before."""
        persistence = InMemoryBackgroundJobRepository()
        old = BaseBackgroundJob.create(job_type="T")
        old.status = BackgroundJobStatus.COMPLETED
        old.updated_at = datetime.now(timezone.utc) - timedelta(days=10)
        await persistence.add(old)
        recent = BaseBackgroundJob.create(job_type="T")
        recent.status = BackgroundJobStatus.COMPLETED
        recent.updated_at = datetime.now(timezone.utc)
        await persistence.add(recent)
        cutoff = datetime.now(timezone.utc) - timedelta(days=5)

        deleted = await persistence.purge_completed(before=cutoff)

        assert deleted == 1
        assert await persistence.get(old.id) is None
        assert await persistence.get(recent.id) is not None


# ============================================================================
# Tests: BackgroundJobAdminService
# ============================================================================


class TestBackgroundJobAdminService:
    """Test the BackgroundJobAdminService."""

    @pytest.mark.asyncio
    async def test_get_statistics_returns_counts_and_total(self) -> None:
        """get_statistics() returns JobStatistics with counts and total."""
        persistence = InMemoryBackgroundJobRepository()
        for _ in range(2):
            j = BaseBackgroundJob.create(job_type="T")
            j.status = BackgroundJobStatus.PENDING
            await persistence.add(j)
        j3 = BaseBackgroundJob.create(job_type="T")
        j3.status = BackgroundJobStatus.FAILED
        await persistence.add(j3)
        admin = BackgroundJobAdminService(repository=persistence)

        stats = await admin.get_statistics()

        assert stats.counts.get("PENDING") == 2
        assert stats.counts.get("FAILED") == 1
        assert stats.total == 3

    @pytest.mark.asyncio
    async def test_list_jobs_filters_by_status(self) -> None:
        """list_jobs() with statuses returns only matching jobs."""
        persistence = InMemoryBackgroundJobRepository()
        failed = BaseBackgroundJob.create(job_type="T")
        failed.status = BackgroundJobStatus.FAILED
        await persistence.add(failed)
        pending = BaseBackgroundJob.create(job_type="T")
        await persistence.add(pending)
        admin = BackgroundJobAdminService(repository=persistence)

        result = await admin.list_jobs(
            statuses=[BackgroundJobStatus.FAILED], limit=10, offset=0
        )

        assert len(result) == 1
        assert result[0].id == failed.id

    @pytest.mark.asyncio
    async def test_bulk_cancel_cancels_cancellable_jobs(self) -> None:
        """bulk_cancel() cancels PENDING/RUNNING jobs, skips terminal."""
        persistence = InMemoryBackgroundJobRepository()
        p = BaseBackgroundJob.create(job_type="T")
        await persistence.add(p)
        r = BaseBackgroundJob.create(job_type="T")
        r.start_processing()
        await persistence.add(r)
        c = BaseBackgroundJob.create(job_type="T")
        c.status = BackgroundJobStatus.COMPLETED
        await persistence.add(c)
        admin = BackgroundJobAdminService(repository=persistence)

        cancelled, skipped = await admin.bulk_cancel([p.id, r.id, c.id])

        assert cancelled == 2
        assert skipped == 1
        assert (await persistence.get(p.id)).status == BackgroundJobStatus.CANCELLED
        assert (await persistence.get(r.id)).status == BackgroundJobStatus.CANCELLED
        assert (await persistence.get(c.id)).status == BackgroundJobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_bulk_retry_retries_failed_within_budget(self) -> None:
        """bulk_retry() retries FAILED jobs within max_retries."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="T", max_retries=3)
        job.fail("err")
        await persistence.add(job)
        admin = BackgroundJobAdminService(repository=persistence)

        retried, skipped = await admin.bulk_retry([job.id])

        assert retried == 1
        assert skipped == 0
        assert (await persistence.get(job.id)).status == BackgroundJobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_purge_completed_deletes_old_terminal_jobs(self) -> None:
        """purge_completed() deletes COMPLETED/CANCELLED before cutoff."""
        persistence = InMemoryBackgroundJobRepository()
        old = BaseBackgroundJob.create(job_type="T")
        old.status = BackgroundJobStatus.CANCELLED
        old.updated_at = datetime.now(timezone.utc) - timedelta(days=10)
        await persistence.add(old)
        admin = BackgroundJobAdminService(repository=persistence)
        cutoff = datetime.now(timezone.utc) - timedelta(days=5)

        deleted = await admin.purge_completed(before=cutoff)

        assert deleted == 1
        assert await persistence.get(old.id) is None

    @pytest.mark.asyncio
    async def test_cancel_running_marks_cancelled_without_kill_strategy(
        self,
    ) -> None:
        """cancel_running() without kill_strategy marks job CANCELLED and returns."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="T")
        job.start_processing()
        await persistence.add(job)
        admin = BackgroundJobAdminService(repository=persistence)

        result = await admin.cancel_running(job.id)

        assert result is not None
        assert result.status == BackgroundJobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_running_non_running_returns_as_is(self) -> None:
        """cancel_running() on PENDING job returns job without changing state."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="T")
        await persistence.add(job)
        admin = BackgroundJobAdminService(repository=persistence)

        result = await admin.cancel_running(job.id)

        assert result is not None
        assert result.status == BackgroundJobStatus.PENDING

    @pytest.mark.asyncio
    async def test_list_jobs_empty_statuses_returns_all_via_list_all(self) -> None:
        """list_jobs() with None or empty statuses delegates to list_all()."""
        persistence = InMemoryBackgroundJobRepository()
        job1 = BaseBackgroundJob.create(job_type="A")
        job2 = BaseBackgroundJob.create(job_type="B")
        await persistence.add(job1)
        await persistence.add(job2)
        admin = BackgroundJobAdminService(repository=persistence)

        result = await admin.list_jobs(statuses=None)

        assert len(result) == 2
        assert {j.id for j in result} == {job1.id, job2.id}

    @pytest.mark.asyncio
    async def test_bulk_cancel_nonexistent_ids_skipped(self) -> None:
        """bulk_cancel() skips nonexistent job IDs and counts skipped."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="T")
        await persistence.add(job)
        admin = BackgroundJobAdminService(repository=persistence)

        cancelled, skipped = await admin.bulk_cancel([job.id, "nonexistent"])

        assert cancelled == 1
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_bulk_cancel_exception_during_cancel_skipped(self) -> None:
        """bulk_cancel() catches exception from cancel() and skips."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="T")
        await persistence.add(job)
        original_add = persistence.add
        call_count = [0]

        async def fail_on_second_add(entity: Any) -> str:
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Persistence error")
            return await original_add(entity)

        persistence.add = fail_on_second_add
        admin = BackgroundJobAdminService(repository=persistence)
        job2 = BaseBackgroundJob.create(job_type="T2")
        await persistence.add(job2)

        cancelled, skipped = await admin.bulk_cancel([job.id, job2.id])

        assert cancelled == 1
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_cancel_running_not_found_returns_none(self) -> None:
        """cancel_running() returns None when job does not exist."""
        persistence = InMemoryBackgroundJobRepository()
        admin = BackgroundJobAdminService(repository=persistence)

        result = await admin.cancel_running("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_running_with_kill_strategy_stops_gracefully(
        self,
    ) -> None:
        """cancel_running() with kill_strategy returns once job is no longer RUNNING (e.g. CANCELLED)."""
        persistence = InMemoryBackgroundJobRepository()
        registry = AsyncioJobTaskRegistry()
        job = BaseBackgroundJob.create(job_type="T")
        job.start_processing()
        await persistence.add(job)
        admin = BackgroundJobAdminService(repository=persistence)

        result = await admin.cancel_running(
            job.id, kill_strategy=registry, grace_seconds=2.0
        )

        assert result is not None
        assert result.status == BackgroundJobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_running_with_kill_strategy_force_kill_marks_failed(
        self,
    ) -> None:
        """When repo still returns RUNNING after grace, force_kill and mark FAILED."""

        # Stub: get() always returns job with RUNNING so poll never exits and we hit force_kill + fail.
        class AlwaysRunningRepo:
            def __init__(self) -> None:
                self._store: dict[str, BaseBackgroundJob] = {}

            async def add(self, entity: BaseBackgroundJob) -> str:
                self._store[entity.id] = entity
                return entity.id

            async def get(self, job_id: str) -> BaseBackgroundJob | None:
                j = self._store.get(job_id)
                if not j:
                    return None
                return j.model_copy(update={"status": BackgroundJobStatus.RUNNING})

        persistence = AlwaysRunningRepo()
        registry = AsyncioJobTaskRegistry()
        job = BaseBackgroundJob.create(job_type="T")
        job.start_processing()
        await persistence.add(job)
        admin = BackgroundJobAdminService(repository=persistence)

        result = await admin.cancel_running(
            job.id, kill_strategy=registry, grace_seconds=0.6
        )

        assert result is not None
        assert result.status == BackgroundJobStatus.FAILED
        assert "grace period" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_bulk_retry_nonexistent_skipped(self) -> None:
        """bulk_retry() skips nonexistent job IDs."""
        persistence = InMemoryBackgroundJobRepository()
        admin = BackgroundJobAdminService(repository=persistence)

        retried, skipped = await admin.bulk_retry(["nonexistent"])

        assert retried == 0
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_bulk_retry_non_failed_skipped(self) -> None:
        """bulk_retry() skips jobs that are not FAILED."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="T")
        job.status = BackgroundJobStatus.PENDING
        await persistence.add(job)
        admin = BackgroundJobAdminService(repository=persistence)

        retried, skipped = await admin.bulk_retry([job.id])

        assert retried == 0
        assert skipped == 1
        assert (await persistence.get(job.id)).status == BackgroundJobStatus.PENDING

    @pytest.mark.asyncio
    async def test_bulk_retry_exhausted_retries_skipped(self) -> None:
        """bulk_retry() skips FAILED jobs that have exhausted max_retries."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="T", max_retries=1)
        job.fail("err")
        job.retry_count = 1
        await persistence.add(job)
        admin = BackgroundJobAdminService(repository=persistence)

        retried, skipped = await admin.bulk_retry([job.id])

        assert retried == 0
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_bulk_retry_job_state_error_skipped(self) -> None:
        """bulk_retry() catches JobStateError during add and skips (race condition)."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="T", max_retries=3)
        job.fail("err")
        await persistence.add(job)
        original_add = persistence.add

        async def add_raise_on_running(entity: Any) -> str:
            await original_add(entity)
            if getattr(entity, "status", None) == BackgroundJobStatus.RUNNING:
                raise JobStateError("concurrent state change")
            return entity.id

        persistence.add = add_raise_on_running
        admin = BackgroundJobAdminService(repository=persistence)

        retried, skipped = await admin.bulk_retry([job.id])

        assert retried == 0
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_purge_completed_default_before_uses_now(self) -> None:
        """purge_completed() with before=None uses current time as threshold."""
        persistence = InMemoryBackgroundJobRepository()
        job = BaseBackgroundJob.create(job_type="T")
        job.status = BackgroundJobStatus.COMPLETED
        job.updated_at = datetime.now(timezone.utc) + timedelta(seconds=10)
        await persistence.add(job)
        admin = BackgroundJobAdminService(repository=persistence)

        deleted = await admin.purge_completed()

        # Job's updated_at is after threshold (now), so not deleted
        assert deleted == 0
        assert await persistence.get(job.id) is not None

    @pytest.mark.asyncio
    async def test_purge_completed_naive_datetime_normalized_to_utc(
        self,
    ) -> None:
        """purge_completed() normalizes naive before to UTC."""
        persistence = InMemoryBackgroundJobRepository()
        old = BaseBackgroundJob.create(job_type="T")
        old.status = BackgroundJobStatus.CANCELLED
        old.updated_at = datetime.now(timezone.utc) - timedelta(days=10)
        await persistence.add(old)
        admin = BackgroundJobAdminService(repository=persistence)
        naive_cutoff = datetime.now() - timedelta(days=5)

        deleted = await admin.purge_completed(before=naive_cutoff)

        assert deleted == 1
        assert await persistence.get(old.id) is None


# ============================================================================
# Tests: Cooperative cancellation and on_cancellation
# ============================================================================


class TestHandlerCooperativeCancellation:
    """Test checkpoint_cancellation and on_cancellation hook."""

    @pytest.mark.asyncio
    async def test_checkpoint_cancellation_raises_when_cancelled(self) -> None:
        """checkpoint_cancellation() raises CancellationRequestedError if job cancelled."""
        persistence = InMemoryBackgroundJobRepository()
        handler = DummyJobEventHandler(persistence)
        job = BaseBackgroundJob.create(job_type="T")
        job.cancel()
        await persistence.add(job)

        with pytest.raises(CancellationRequestedError, match="cancelled"):
            await handler.checkpoint_cancellation(job.id)

    @pytest.mark.asyncio
    async def test_checkpoint_cancellation_does_not_raise_when_running(
        self,
    ) -> None:
        """checkpoint_cancellation() does not raise when job is RUNNING."""
        persistence = InMemoryBackgroundJobRepository()
        handler = DummyJobEventHandler(persistence)
        job = BaseBackgroundJob.create(job_type="T")
        job.start_processing()
        await persistence.add(job)

        await handler.checkpoint_cancellation(job.id)
        # No raise

    @pytest.mark.asyncio
    async def test_on_cancellation_hook_called_on_cooperative_cancel(self) -> None:
        """When execute raises CancellationRequestedError, on_cancellation is called."""

        class CancelCheckpointHandler(DummyJobEventHandler):
            def __init__(self, persistence: Any) -> None:
                super().__init__(persistence)
                self.on_cancellation_called = False

            async def execute(
                self, event: DomainEvent, job: BaseBackgroundJob
            ) -> dict[str, Any] | None:
                job_from_db = await self._persistence.get(job.id)
                if job_from_db:
                    job_from_db.cancel()
                    await self._persistence.add(job_from_db)
                await self.checkpoint_cancellation(job.id)
                return None

            async def on_cancellation(
                self, event: DomainEvent, job: BaseBackgroundJob
            ) -> None:
                self.on_cancellation_called = True

        persistence = InMemoryBackgroundJobRepository()
        handler = CancelCheckpointHandler(persistence)
        job = BaseBackgroundJob.create(job_type="T")
        job.correlation_id = job.id
        await persistence.add(job)
        event = JobCreated(job_type="T", correlation_id=job.id)

        await handler.handle(event)

        assert handler.on_cancellation_called
        stored = await persistence.get(job.id)
        assert stored.status == BackgroundJobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancellation_requested_error_ends_in_cancelled_state(
        self,
    ) -> None:
        """When checkpoint_cancellation raises, job is persisted as CANCELLED."""
        persistence = InMemoryBackgroundJobRepository()

        class HandlerThatCancelsThenCheckpoints(DummyJobEventHandler):
            async def execute(
                self, event: DomainEvent, job: BaseBackgroundJob
            ) -> dict[str, Any] | None:
                latest = await self._persistence.get(job.id)
                if latest:
                    latest.cancel()
                    await self._persistence.add(latest)
                await self.checkpoint_cancellation(job.id)
                return {"done": True}

        handler = HandlerThatCancelsThenCheckpoints(persistence)
        job = BaseBackgroundJob.create(job_type="T")
        job.correlation_id = job.id
        await persistence.add(job)
        event = JobCreated(job_type="T", correlation_id=job.id)
        await handler.handle(event)

        stored = await persistence.get(job.id)
        assert stored.status == BackgroundJobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_handle_reload_sees_cancelled_skips_completion(
        self,
    ) -> None:
        """After execute() returns, if reload sees CANCELLED we skip complete()."""
        persistence = InMemoryBackgroundJobRepository()

        class HandlerThatCancelsDuringExecute(DummyJobEventHandler):
            async def execute(
                self, event: DomainEvent, job: BaseBackgroundJob
            ) -> dict[str, Any] | None:
                # Simulate admin cancelling during execute: persist CANCELLED.
                latest = await self._persistence.get(job.id)
                if latest:
                    latest.cancel()
                    await self._persistence.add(latest)
                return {"would_complete": True}

        handler = HandlerThatCancelsDuringExecute(persistence)
        job = BaseBackgroundJob.create(job_type="T")
        job.correlation_id = job.id
        await persistence.add(job)
        event = JobCreated(job_type="T", correlation_id=job.id)
        await handler.handle(event)

        stored = await persistence.get(job.id)
        assert stored.status == BackgroundJobStatus.CANCELLED
        # We did not call complete(); result_data may be default {} from cancel() or entity init

    @pytest.mark.asyncio
    async def test_handle_cancellation_persists_when_store_still_running(
        self,
    ) -> None:
        """When CancellationRequestedError is raised and store still RUNNING, _handle_cancellation persists CANCELLED."""
        persistence = InMemoryBackgroundJobRepository()

        class HandlerThatRaisesCancel(DummyJobEventHandler):
            async def execute(
                self, event: DomainEvent, job: BaseBackgroundJob
            ) -> dict[str, Any] | None:
                raise CancellationRequestedError("cancelled")

        handler = HandlerThatRaisesCancel(persistence)
        job = BaseBackgroundJob.create(job_type="T")
        job.correlation_id = job.id
        await persistence.add(job)
        event = JobCreated(job_type="T", correlation_id=job.id)
        await handler.handle(event)

        stored = await persistence.get(job.id)
        assert stored.status == BackgroundJobStatus.CANCELLED


# ============================================================================
# Tests: AsyncioJobTaskRegistry
# ============================================================================


class TestAsyncioJobTaskRegistry:
    """Test AsyncioJobTaskRegistry (IJobKillStrategy)."""

    @pytest.mark.asyncio
    async def test_register_and_unregister(self) -> None:
        """register() stores task, unregister() removes it."""
        registry = AsyncioJobTaskRegistry()
        task = asyncio.create_task(asyncio.sleep(10))

        registry.register("job-1", task)
        registry.unregister("job-1")

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_request_stop_cancels_task(self) -> None:
        """request_stop() cancels the asyncio task."""
        registry = AsyncioJobTaskRegistry()
        task = asyncio.create_task(asyncio.sleep(60))
        registry.register("job-1", task)

        await registry.request_stop("job-1")

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_register_rejects_non_task(self) -> None:
        """register() with non-Task raises TypeError."""
        registry = AsyncioJobTaskRegistry()

        with pytest.raises(TypeError, match="asyncio.Task"):
            registry.register("job-1", "not a task")

    @pytest.mark.asyncio
    async def test_force_kill_cancels_task(self) -> None:
        """force_kill() cancels the asyncio task (same as request_stop for asyncio)."""
        registry = AsyncioJobTaskRegistry()
        task = asyncio.create_task(asyncio.sleep(60))
        registry.register("job-1", task)

        await registry.force_kill("job-1")

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_request_stop_unknown_job_id_no_op(self) -> None:
        """request_stop() for unknown job_id does nothing."""
        registry = AsyncioJobTaskRegistry()
        await registry.request_stop("unknown")

    @pytest.mark.asyncio
    async def test_unregister_unknown_job_id_no_op(self) -> None:
        """unregister() for unknown job_id does nothing."""
        registry = AsyncioJobTaskRegistry()
        registry.unregister("unknown")


# ============================================================================
# Fixtures
# ============================================================================


class DummyUnitOfWork:
    """Mock UnitOfWork for testing."""

    async def __aenter__(self) -> DummyUnitOfWork:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


# ============================================================================
# BackgroundJobService additional tests
# ============================================================================


class TestBackgroundJobServiceExtended:
    """Extended tests for BackgroundJobService methods."""

    @pytest.mark.asyncio
    async def test_cancel_existing_job(self) -> None:
        """cancel() should cancel an existing job."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        # Create and schedule a pending job
        job = BaseBackgroundJob.create(job_type="Task")
        await service.schedule(job)

        # Cancel the job
        result = await service.cancel(job.id)

        assert result is not None
        assert result.status == BackgroundJobStatus.CANCELLED
        assert result.id == job.id

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self) -> None:
        """cancel() should return None for nonexistent job."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        result = await service.cancel("nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_retry_failed_job(self) -> None:
        """retry() should retry a failed job."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        # Create a job, start it, then fail it
        job = BaseBackgroundJob.create(job_type="Task")
        await service.schedule(job)
        job.start_processing()
        job.fail("Initial failure")
        await persistence.add(job)

        # Retry the job
        result = await service.retry(job.id)

        assert result is not None
        assert result.status == BackgroundJobStatus.RUNNING
        assert result.retry_count == 1

    @pytest.mark.asyncio
    async def test_retry_nonexistent_job(self) -> None:
        """retry() should return None for nonexistent job."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        result = await service.retry("nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_mark_running_transitions_state(self) -> None:
        """mark_running() should transition PENDING job to RUNNING."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        # Create a pending job
        job = BaseBackgroundJob.create(job_type="Task")
        await service.schedule(job)

        # Mark as running
        result = await service.mark_running(job.id)

        assert result is not None
        assert result.status == BackgroundJobStatus.RUNNING
        assert result.id == job.id

    @pytest.mark.asyncio
    async def test_mark_running_triggers_sweeper(self) -> None:
        """mark_running() should trigger sweeper callback if set."""
        persistence = InMemoryBackgroundJobRepository()
        sweeper_triggered = False

        def sweeper_trigger():
            nonlocal sweeper_triggered
            sweeper_triggered = True

        service = BackgroundJobService(persistence, sweeper_trigger=sweeper_trigger)

        # Create and schedule a job
        job = BaseBackgroundJob.create(job_type="Task")
        await service.schedule(job)

        # Mark as running
        await service.mark_running(job.id)

        assert sweeper_triggered

    @pytest.mark.asyncio
    async def test_mark_running_handles_sweeper_failure(self) -> None:
        """mark_running() should handle sweeper trigger failures gracefully."""
        persistence = InMemoryBackgroundJobRepository()

        def failing_sweeper():
            raise Exception("Sweeper error")

        service = BackgroundJobService(persistence, sweeper_trigger=failing_sweeper)

        # Create and schedule a job
        job = BaseBackgroundJob.create(job_type="Task")
        await service.schedule(job)

        # Mark as running - should not raise despite sweeper failure
        result = await service.mark_running(job.id)

        assert result is not None
        assert result.status == BackgroundJobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_mark_running_nonexistent_job(self) -> None:
        """mark_running() should return None for nonexistent job."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        result = await service.mark_running("nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_process_stale_jobs_marks_as_failed(self) -> None:
        """process_stale_jobs() should mark stale jobs as failed."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        # Create running jobs that are stale
        job1 = BaseBackgroundJob.create(job_type="Task", timeout_seconds=60)
        job1.status = BackgroundJobStatus.RUNNING
        job1.updated_at = datetime.now(timezone.utc) - timedelta(
            seconds=120
        )  # 2 minutes old
        await persistence.add(job1)

        job2 = BaseBackgroundJob.create(job_type="Task", timeout_seconds=60)
        job2.status = BackgroundJobStatus.RUNNING
        job2.updated_at = datetime.now(timezone.utc) - timedelta(
            seconds=90
        )  # 1.5 minutes old
        await persistence.add(job2)

        # Process stale jobs with 60 second timeout
        swept_count = await service.process_stale_jobs(timeout_seconds=60)

        assert swept_count == 2

        # Verify jobs are marked as failed
        job1_after = await persistence.get(job1.id)
        job2_after = await persistence.get(job2.id)
        assert job1_after.status == BackgroundJobStatus.FAILED
        assert job2_after.status == BackgroundJobStatus.FAILED
        assert "timed out" in job1_after.error_message.lower()

    @pytest.mark.asyncio
    async def test_process_stale_jobs_no_stale_jobs(self) -> None:
        """process_stale_jobs() should return 0 when no stale jobs."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        # Create a recent running job
        job = BaseBackgroundJob.create(job_type="Task")
        job.status = BackgroundJobStatus.RUNNING
        job.updated_at = datetime.now(timezone.utc)  # Fresh
        await persistence.add(job)

        swept_count = await service.process_stale_jobs(timeout_seconds=60)

        assert swept_count == 0

        # Verify job is still running
        job_after = await persistence.get(job.id)
        assert job_after.status == BackgroundJobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_process_stale_jobs_handles_sweep_failure(self) -> None:
        """process_stale_jobs() should handle individual job sweep failures."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        # Create two stale jobs
        job1 = BaseBackgroundJob.create(job_type="Task1")
        job1.start_processing()
        job1.updated_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        await persistence.add(job1)

        job2 = BaseBackgroundJob.create(job_type="Task2")
        job2.start_processing()
        job2.updated_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        await persistence.add(job2)

        # Mock persistence to fail on the second sweep attempt
        original_add = persistence.add
        add_calls = [0]

        async def failing_add(job_arg):
            add_calls[0] += 1
            if add_calls[0] == 2:  # Fail on second sweep attempt
                raise Exception("Persistence error during sweep")
            return await original_add(job_arg)

        persistence.add = failing_add

        # Process should handle the error gracefully
        swept_count = await service.process_stale_jobs(timeout_seconds=60)

        # First job succeeds (swept=1), second job fails (exception caught, swept stays 1)
        assert swept_count == 1
        assert add_calls[0] == 2  # Both jobs attempted persistence

    @pytest.mark.asyncio
    async def test_set_sweeper_trigger(self) -> None:
        """set_sweeper_trigger() should update the sweeper callback."""
        persistence = InMemoryBackgroundJobRepository()
        service = BackgroundJobService(persistence)

        # Initially no sweeper
        assert service._sweeper_trigger is None

        # Set sweeper
        triggered = False

        def sweeper():
            nonlocal triggered
            triggered = True

        service.set_sweeper_trigger(sweeper)

        # Create and mark running to trigger sweeper
        job = BaseBackgroundJob.create(job_type="Task")
        await service.schedule(job)
        await service.mark_running(job.id)

        assert triggered
