"""
Advanced persistence components.
"""

from __future__ import annotations

from .jobs import SQLAlchemyBackgroundJobRepository
from .models import (
    BackgroundJobModel,
    JobStatus,
    SagaStateModel,
    SagaStatus,
    ScheduledCommandModel,
    SnapshotModel,
)
from .persistence import (
    SQLAlchemyOperationPersistence,
    SQLAlchemyQueryPersistence,
    SQLAlchemyQuerySpecificationPersistence,
    SQLAlchemyRetrievalPersistence,
)
from .saga import SQLAlchemySagaRepository
from .scheduling import SQLAlchemyCommandScheduler
from .snapshots import SQLAlchemySnapshotStore

__all__ = [
    "SQLAlchemySagaRepository",
    "SQLAlchemyBackgroundJobRepository",
    "SQLAlchemyCommandScheduler",
    "SQLAlchemySnapshotStore",
    "SagaStateModel",
    "SagaStatus",
    "BackgroundJobModel",
    "JobStatus",
    "ScheduledCommandModel",
    "SnapshotModel",
    # Dispatcher persistence bases
    "SQLAlchemyOperationPersistence",
    "SQLAlchemyRetrievalPersistence",
    "SQLAlchemyQueryPersistence",
    "SQLAlchemyQuerySpecificationPersistence",
]
