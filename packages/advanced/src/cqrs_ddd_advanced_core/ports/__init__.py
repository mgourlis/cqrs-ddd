"""Infrastructure port protocols for cqrs-ddd-advanced-core."""

from __future__ import annotations

from .background_jobs import IBackgroundJobRepository
from .conflict import IMergeStrategy
from .persistence import (
    T_ID,
    IOperationPersistence,
    IQueryPersistence,
    IQuerySpecificationPersistence,
    IRetrievalPersistence,
    T_Criteria,
)
from .saga_repository import ISagaRepository
from .scheduling import ICommandScheduler
from .snapshots import ISnapshotStore, ISnapshotStrategy
from .undo import IUndoExecutor, IUndoExecutorRegistry
from .upcasting import IEventUpcaster

__all__ = [
    # Sagas
    "ISagaRepository",
    # Background
    "IBackgroundJobRepository",
    # Undo/Redo
    "IUndoExecutor",
    "IUndoExecutorRegistry",
    # Persistence
    "IOperationPersistence",
    "IRetrievalPersistence",
    "IQueryPersistence",
    "IQuerySpecificationPersistence",
    "T_Criteria",
    "T_ID",
    # Scheduling
    "ICommandScheduler",
    # Upcasting
    "IEventUpcaster",
    # Snapshots
    "ISnapshotStore",
    "ISnapshotStrategy",
    # Conflict
    "IMergeStrategy",
]
