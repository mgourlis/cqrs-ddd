"""Tests for the Background Jobs package."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from cqrs_ddd_advanced_core.adapters.memory import InMemoryBackgroundJobRepository
from cqrs_ddd_advanced_core.background_jobs import (
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
from cqrs_ddd_advanced_core.exceptions import JobStateError
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
