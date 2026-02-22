"""Background Job Management — entity, events, services, worker, handler."""

from __future__ import annotations

from ..exceptions import CancellationRequestedError
from .admin_service import BackgroundJobAdminService, JobStatistics
from .entity import BackgroundJobStatus, BaseBackgroundJob
from .events import (
    JobCancelled,
    JobCompleted,
    JobCreated,
    JobFailed,
    JobRetried,
    JobStarted,
)
from .handler import BackgroundJobEventHandler
from .service import BackgroundJobService
from .worker import JobSweeperWorker

__all__ = [
    # Entity
    "BackgroundJobStatus",
    "BaseBackgroundJob",
    # Events
    "JobCreated",
    "JobStarted",
    "JobCompleted",
    "JobFailed",
    "JobRetried",
    "JobCancelled",
    # Exceptions
    "CancellationRequestedError",
    "BackgroundJobService",
    "BackgroundJobAdminService",
    "JobStatistics",
    # Worker
    "JobSweeperWorker",
    # Handler
    "BackgroundJobEventHandler",
]
