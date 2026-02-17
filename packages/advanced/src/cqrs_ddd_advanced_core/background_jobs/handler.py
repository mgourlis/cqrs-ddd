"""BackgroundJobEventHandler — generic handler that processes jobs on event arrival."""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from cqrs_ddd_core.cqrs.handler import EventHandler
from cqrs_ddd_core.domain.events import DomainEvent

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
        5a. Success → ``complete()``
        5b. Failure → ``on_failure()`` hook → ``fail()``
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
            job.complete(result)
            await self._persistence.add(job)
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
