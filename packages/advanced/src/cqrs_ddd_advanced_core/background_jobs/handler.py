"""BackgroundJobEventHandler — generic handler that processes jobs on event arrival."""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from cqrs_ddd_core.cqrs.handler import EventHandler
from cqrs_ddd_core.domain.events import DomainEvent

from ..exceptions import CancellationRequestedError
from .entity import BackgroundJobStatus, BaseBackgroundJob

if TYPE_CHECKING:
    from ..ports.background_jobs import IBackgroundJobRepository

logger = logging.getLogger("cqrs_ddd.background_jobs")

TEvent = TypeVar("TEvent", bound=DomainEvent)


class BackgroundJobEventHandler(EventHandler[TEvent], Generic[TEvent]):
    """Generic handler that loads a job, runs domain logic, and persists the result.

    Subclasses implement :meth:`execute` with the actual task logic.

    Lifecycle::

        1. Load job via ``correlation_id``
        2. ``before_processing()`` hook (optional)
        3. ``start_processing()``
        4. ``execute()``
        5a. Success → reload from repo, ``complete()`` if not cancelled
        5b. CancellationRequestedError → ``on_cancellation()`` hook →
            ensure CANCELLED state, return
        5c. Other failure → ``on_failure()`` hook → ``fail()``

    Cooperative cancellation:

        Long-running ``execute()`` implementations should periodically call
        :meth:`checkpoint_cancellation` to detect admin-initiated cancellation
        and stop early.
    """

    def __init__(
        self,
        persistence: IBackgroundJobRepository,
    ) -> None:
        self._persistence = persistence

    # -- abstract ---------------------------------------------------------

    @abstractmethod
    async def execute(
        self, event: TEvent, job: BaseBackgroundJob
    ) -> dict[str, Any] | None:
        """Run the actual background task. Return optional result data."""
        ...

    # -- hooks (override if needed) ----------------------------------------

    async def before_processing(self, event: TEvent, job: BaseBackgroundJob) -> None:
        """Called before the job moves to RUNNING.

        Useful for injecting broker metadata (e.g. message ID).
        """

    async def on_failure(
        self, event: TEvent, job: BaseBackgroundJob, error: Exception
    ) -> None:
        """Called after a job execution error — before ``fail()``."""

    async def on_cancellation(self, event: TEvent, job: BaseBackgroundJob) -> None:
        """Called when the job is stopped by cooperative cancellation.

        Override to release resources, delete temp files, or send
        notifications. Runs before the job is persisted as CANCELLED.
        """

    # -- cooperative cancellation -----------------------------------------

    async def checkpoint_cancellation(self, job_id: str) -> None:
        """Poll the repository and raise if the job has been cancelled.

        Call this periodically inside :meth:`execute` (e.g. between batches)
        to enable cooperative cancellation of long-running work::

            for batch in batches:
                await self.checkpoint_cancellation(job.id)
                await process(batch)
                job.update_progress(processed)
                await self._persistence.add(job)

        Raises:
            CancellationRequestedError: if the persisted status is CANCELLED.
        """
        if await self._persistence.is_cancellation_requested(job_id):
            raise CancellationRequestedError(f"Job {job_id} was cancelled")

    # -- main entry -------------------------------------------------------

    async def handle(self, event: TEvent) -> None:
        job_id = event.correlation_id
        if not job_id:
            logger.warning(
                "Event %s missing correlation_id — cannot link to background job",
                type(event).__name__,
            )
            return

        # 1. Load
        job = await self._persistence.get(job_id)
        if not job:
            logger.warning("Background job %s not found", job_id)
            return

        # 2. Before hook
        await self.before_processing(event, job)

        # 3. Start (or retry if previously failed)
        if job.status == BackgroundJobStatus.FAILED:
            job.retry()
        else:
            job.start_processing()
        await self._persistence.add(job)

        # 4. Execute
        try:
            result = await self.execute(event, job)

            # Guard against concurrent cancellation: reload fresh state.
            latest = await self._persistence.get(job_id)
            if latest and latest.status == BackgroundJobStatus.CANCELLED:
                logger.info(
                    "Job %s cancelled during execution — skipping completion",
                    job_id,
                )
                return

            job.complete(result)
            await self._persistence.add(job)

        except CancellationRequestedError:
            await self.on_cancellation(event, job)
            await self._handle_cancellation(job_id)

        except Exception as exc:
            logger.exception("Background job %s failed", job_id)
            await self.on_failure(event, job, exc)

            # Only fail if not already terminal
            if job.status not in (
                BackgroundJobStatus.COMPLETED,
                BackgroundJobStatus.FAILED,
                BackgroundJobStatus.CANCELLED,
            ):
                job.fail(str(exc))
                await self._persistence.add(job)
            raise

    # -- internal ---------------------------------------------------------

    async def _handle_cancellation(self, job_id: str) -> None:
        """Ensure the job is persisted in CANCELLED state after cooperative cancel."""
        latest = await self._persistence.get(job_id)
        if not latest:
            return
        if latest.status == BackgroundJobStatus.CANCELLED:
            logger.info("Job %s cooperatively cancelled", job_id)
            return
        # Admin cancel was detected but status hasn't been persisted yet
        # (e.g. in-memory object diverged); force it.
        latest.cancel()
        await self._persistence.add(latest)
        logger.info("Job %s cooperatively cancelled (persisted)", job_id)
