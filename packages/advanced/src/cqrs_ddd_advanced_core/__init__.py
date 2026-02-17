"""cqrs-ddd-advanced-core: Complex business logic patterns for CQRS/DDD."""

from __future__ import annotations

from cqrs_ddd_advanced_core.exceptions import (
    HandlerNotRegisteredError,
    JobStateError,
    MergeStrategyRegistryMissingError,
    ResilienceError,
    SagaConfigurationError,
    SagaHandlerNotFoundError,
    SagaStateError,
    SourceNotRegisteredError,
)
from cqrs_ddd_core.primitives.exceptions import ConcurrencyError, OptimisticLockingError

from .adapters.memory import (
    InMemoryBackgroundJobRepository,
    InMemoryCommandScheduler,
    InMemorySagaRepository,
)
from .background_jobs import (
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

# Conflict Resolution
from .conflict.resolution import (
    ConflictResolutionPolicy,
    ConflictResolver,
    DeepMergeStrategy,
    FieldLevelMergeStrategy,
    MergeStrategyRegistry,
    field_level_merge,
)

# CQRS Handlers and Mixins
from .cqrs.handlers import (
    ConflictCommandHandler,
    ConflictResolutionMixin,
    PipelinedCommandHandler,
    ResilientCommandHandler,
    RetryableCommandHandler,
    RetryBehaviorMixin,
)
from .cqrs.mixins import (
    ConflictConfig,
    ConflictResilient,
    ExponentialBackoffPolicy,
    FixedRetryPolicy,
    Retryable,
    RetryPolicy,
)

# Persistence
from .persistence import PersistenceDispatcher, PersistenceRegistry

# Ports
from .ports import (
    IBackgroundJobRepository,
    ICommandScheduler,
    IEventUpcaster,
    IMergeStrategy,
    IOperationPersistence,
    IQueryPersistence,
    IQuerySpecificationPersistence,
    IRetrievalPersistence,
    ISagaRepository,
    ISnapshotStore,
    ISnapshotStrategy,
    IUndoExecutor,
    IUndoExecutorRegistry,
)

# Sagas
from .sagas import (
    Saga,
    SagaBuilder,
    SagaManager,
    SagaRecoveryWorker,
    SagaRegistry,
    SagaState,
    SagaStatus,
)

# Scheduling
from .scheduling import CommandSchedulerService, CommandSchedulerWorker

# Snapshots
from .snapshots import EveryNEventsStrategy

# Undo/Redo
from .undo import UndoExecutorRegistry, UndoService

# Upcasting
from .upcasting import UpcasterChain

__all__ = [
    # Sagas
    "Saga",
    "SagaBuilder",
    "SagaManager",
    "SagaRegistry",
    "SagaRecoveryWorker",
    "SagaState",
    "SagaStatus",
    "InMemorySagaRepository",
    # Ports
    "ISagaRepository",
    "IBackgroundJobRepository",
    "IUndoExecutor",
    "IUndoExecutorRegistry",
    # Background Jobs
    "BackgroundJobStatus",
    "BaseBackgroundJob",
    "JobCreated",
    "JobStarted",
    "JobCompleted",
    "JobFailed",
    "JobRetried",
    "JobCancelled",
    "BackgroundJobService",
    "JobSweeperWorker",
    "InMemoryBackgroundJobRepository",
    "InMemoryCommandScheduler",
    # Undo/Redo
    "UndoService",
    "UndoExecutorRegistry",
    # Persistence
    "PersistenceDispatcher",
    "PersistenceRegistry",
    "IOperationPersistence",
    "IRetrievalPersistence",
    "IQueryPersistence",
    "IQuerySpecificationPersistence",
    # Snapshots
    "ISnapshotStore",
    "ISnapshotStrategy",
    "EveryNEventsStrategy",
    # Scheduling
    "ICommandScheduler",
    "CommandSchedulerService",
    "CommandSchedulerWorker",
    # Upcasting
    "IEventUpcaster",
    "UpcasterChain",
    # Conflict Resolution
    "ConflictResolutionPolicy",
    "ConflictResolver",
    "field_level_merge",
    "IMergeStrategy",
    "MergeStrategyRegistry",
    "DeepMergeStrategy",
    "FieldLevelMergeStrategy",
    "ConcurrencyError",
    "MergeStrategyRegistryMissingError",
    "ResilienceError",
    "HandlerNotRegisteredError",
    "JobStateError",
    "SagaConfigurationError",
    "SagaHandlerNotFoundError",
    "SagaStateError",
    "SourceNotRegisteredError",
    "OptimisticLockingError",
    # CQRS
    "ConflictConfig",
    "ConflictResilient",
    "Retryable",
    "RetryPolicy",
    "FixedRetryPolicy",
    "ExponentialBackoffPolicy",
    "PipelinedCommandHandler",
    "RetryBehaviorMixin",
    "ConflictResolutionMixin",
    "RetryableCommandHandler",
    "ConflictCommandHandler",
    "ResilientCommandHandler",
]
