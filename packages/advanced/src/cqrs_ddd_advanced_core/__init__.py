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
    InMemorySnapshotStore,
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

# Event Sourcing
from .cqrs.event_sourced_mediator import EventSourcedMediator
from .cqrs.factory import EventSourcedMediatorFactory

# CQRS Handlers and Mixins
from .cqrs.handlers import (
    ConflictCommandHandler,
    ConflictResolutionMixin,
    PipelinedCommandHandler,
    ResilientCommandHandler,
    RetryableCommandHandler,
    RetryBehaviorMixin,
)

# CQRS Handlers and Mixins
from .cqrs.mixins import (
    ConflictConfig,
    ConflictResilient,
    ExponentialBackoffPolicy,
    FixedRetryPolicy,
    Retryable,
    RetryPolicy,
)
from .decorators.event_sourcing import non_event_sourced

# Exceptions
from .domain.exceptions import (
    EventHandlerError,
    EventSourcedAggregateRequiredError,
    EventSourcingConfigurationError,
    InvalidEventHandlerError,
    MissingEventHandlerError,
    StrictValidationViolationError,
)
from .event_sourcing import (
    DefaultEventApplicator,
    EventSourcedLoader,
    EventSourcedRepository,
    UpcastingEventReader,
)
from .event_sourcing.persistence_orchestrator import (
    EventSourcedPersistenceOrchestrator,
)

# Persistence
from .persistence import PersistenceDispatcher, PersistenceRegistry

# Ports
from .ports import (
    IBackgroundJobRepository,
    ICommandScheduler,
    IEventApplicator,
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
from .snapshots import EveryNEventsStrategy, SnapshotStrategyRegistry

# Undo/Redo
from .undo import UndoExecutorRegistry, UndoService

# Upcasting
from .upcasting import EventUpcaster, UpcasterChain, UpcasterRegistry

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
    "InMemorySnapshotStore",
    # Event sourcing
    "DefaultEventApplicator",
    "EventSourcedLoader",
    "EventSourcedMediator",
    "EventSourcedMediatorFactory",
    "EventSourcedPersistenceOrchestrator",
    "EventSourcedRepository",
    "UpcastingEventReader",
    "non_event_sourced",
    "EventHandlerError",
    "MissingEventHandlerError",
    "InvalidEventHandlerError",
    "StrictValidationViolationError",
    "EventSourcedAggregateRequiredError",
    "EventSourcingConfigurationError",
    # Ports
    "ISagaRepository",
    "IEventApplicator",
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
    "SnapshotStrategyRegistry",
    # Scheduling
    "ICommandScheduler",
    "CommandSchedulerService",
    "CommandSchedulerWorker",
    # Upcasting
    "IEventUpcaster",
    "EventUpcaster",
    "UpcasterChain",
    "UpcasterRegistry",
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
