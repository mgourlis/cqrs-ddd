"""Write-to-read sync engine — projection workers, event sink, replay."""

from __future__ import annotations

from .checkpoint import (
    InMemoryCheckpointStore,
)
from .error_handling import ProjectionErrorPolicy
from .exceptions import CheckpointError, ProjectionError, ProjectionHandlerError
from .handler import ProjectionHandler
from .partitioning import PartitionedProjectionWorker
from .ports import ICheckpointStore, IProjectionHandler, IProjectionRegistry
from .registry import ProjectionRegistry
from .replay import ReplayEngine
from .sink import EventSinkRunner
from .worker import ProjectionWorker

__all__ = [
    "CheckpointError",
    "EventSinkRunner",
    "InMemoryCheckpointStore",
    "ICheckpointStore",
    "IProjectionHandler",
    "IProjectionRegistry",
    "PartitionedProjectionWorker",
    "ProjectionError",
    "ProjectionErrorPolicy",
    "ProjectionHandler",
    "ProjectionHandlerError",
    "ProjectionRegistry",
    "ProjectionWorker",
    "ReplayEngine",
]
