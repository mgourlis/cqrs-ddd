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
from .position_store import SQLAlchemyProjectionPositionStore
from .projection_query import (
    SQLAlchemyProjectionDualPersistence,
    SQLAlchemyProjectionQueryPersistence,
    SQLAlchemyProjectionSpecPersistence,
)
from .projection_store import SQLAlchemyProjectionStore
from .saga import SQLAlchemySagaRepository
from .scheduling import SQLAlchemyCommandScheduler
from .snapshots import SQLAlchemySnapshotStore

__all__ = [
    "SQLAlchemyProjectionPositionStore",
    "SQLAlchemyProjectionStore",
    "SQLAlchemyProjectionQueryPersistence",
    "SQLAlchemyProjectionSpecPersistence",
    "SQLAlchemyProjectionDualPersistence",
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
