"""Background Job Management — entity, events, service, worker, handler."""

from __future__ import annotations

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
    # Service
    "BackgroundJobService",
    # Worker
    "JobSweeperWorker",
    # Handler
    "BackgroundJobEventHandler",
]
