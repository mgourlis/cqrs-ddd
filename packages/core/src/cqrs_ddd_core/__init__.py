"""cqrs-ddd-core — Foundation package for the CQRS/DDD toolkit.

Zero infrastructure dependencies. Optional pydantic for validation & schema.
"""

from __future__ import annotations

# ── Adapters ────────────────────────────────────────────────────
from .adapters.memory import (
    InMemoryEventStore,
    InMemoryLockStrategy,
    InMemoryOutboxStorage,
    InMemoryRepository,
    InMemoryUnitOfWork,
)
from .correlation import (
    CorrelationIdPropagator,
    generate_correlation_id,
    get_causation_id,
    get_context_vars,
    get_correlation_id,
    set_causation_id,
    set_context_vars,
    set_correlation_id,
    with_correlation_context,
)

# ── CQRS ─────────────────────────────────────────────────────────
from .cqrs import (
    BaseEventConsumer,
    BufferedOutbox,
    Command,
    CommandHandler,
    CommandResponse,
    EventDispatcher,
    EventHandler,
    HandlerRegistry,
    Mediator,
    OutboxService,
    Query,
    QueryHandler,
    QueryResponse,
    UnitOfWork,
    get_current_uow,
    route_to,
)

# ── Domain ───────────────────────────────────────────────────────
from .domain import (
    HAS_GEO,
    AggregateRoot,
    AggregateRootMixin,
    AuditableMixin,
    DomainEvent,
    EventTypeRegistry,
    ValueObject,
    enrich_event_metadata,
)

if HAS_GEO:
    from .domain import SpatialMixin  # noqa: F401

# ── Middleware ───────────────────────────────────────────────────
from .instrumentation import (
    HookRegistration,
    HookRegistry,
    InstrumentationHook,
    fire_and_forget_hook,
    get_hook_registry,
    set_hook_registry,
)
from .middleware import (
    EventStorePersistenceMiddleware,
    LoggingMiddleware,
    MiddlewareDefinition,
    MiddlewareRegistry,
    OutboxMiddleware,
    ValidatorMiddleware,
    build_pipeline,
)

# ── Ports ────────────────────────────────────────────────────────
from .ports import (
    ICommandBus,
    IEventDispatcher,
    IEventStore,
    ILockStrategy,
    IMessageConsumer,
    IMessagePublisher,
    IMiddleware,
    IOutboxStorage,
    IQueryBus,
    IRepository,
    IValidator,
    OutboxMessage,
    StoredEvent,
)

# ── Primitives ──────────────────────────────────────────────────
from .primitives import (
    ConcurrencyError,
    CQRSDDDError,
    DomainConcurrencyError,
    DomainError,
    EntityNotFoundError,
    EventStoreError,
    HandlerError,
    HandlerRegistrationError,
    IIDGenerator,
    InvariantViolationError,
    NotFoundError,
    OptimisticLockingError,
    OutboxError,
    PublisherNotFoundError,
    UUID4Generator,
    ValidationError,
)

# ── Validation ──────────────────────────────────────────────────
from .validation import CompositeValidator, PydanticValidator, ValidationResult

__all__: list[str] = [
    # Domain
    "AggregateRoot",
    "AggregateRootMixin",
    "AuditableMixin",
    "DomainEvent",
    "EventTypeRegistry",
    "HAS_GEO",
    "ValueObject",
    "enrich_event_metadata",
    # CQRS
    "Command",
    "CommandHandler",
    "CommandResponse",
    "EventDispatcher",
    "EventHandler",
    "HandlerRegistry",
    "ICommandBus",
    "IQueryBus",
    "Mediator",
    "Query",
    "QueryHandler",
    "QueryResponse",
    "get_current_uow",
    "UnitOfWork",
    "route_to",
    "CorrelationIdPropagator",
    "generate_correlation_id",
    "get_correlation_id",
    "set_correlation_id",
    "get_causation_id",
    "set_causation_id",
    "get_context_vars",
    "set_context_vars",
    "with_correlation_context",
    # Ports
    "IEventDispatcher",
    "IEventStore",
    "IMessageConsumer",
    "IMessagePublisher",
    "IMiddleware",
    "IOutboxStorage",
    "IRepository",
    "IValidator",
    "OutboxMessage",
    "StoredEvent",
    # Middleware
    "EventStorePersistenceMiddleware",
    "LoggingMiddleware",
    "MiddlewareDefinition",
    "MiddlewareRegistry",
    "OutboxMiddleware",
    "ValidatorMiddleware",
    "build_pipeline",
    "InstrumentationHook",
    "HookRegistration",
    "HookRegistry",
    "fire_and_forget_hook",
    "get_hook_registry",
    "set_hook_registry",
    # Validation
    "CompositeValidator",
    "PydanticValidator",
    "ValidationResult",
    # Primitives
    "CQRSDDDError",
    "ConcurrencyError",
    "DomainConcurrencyError",
    "OptimisticLockingError",
    "DomainError",
    "EntityNotFoundError",
    "EventStoreError",
    "HandlerError",
    "HandlerRegistrationError",
    "IIDGenerator",
    "InvariantViolationError",
    "NotFoundError",
    "OutboxError",
    "PublisherNotFoundError",
    "UUID4Generator",
    "ValidationError",
    "BufferedOutbox",
    "OutboxService",
    "BaseEventConsumer",
    # Adapters
    "InMemoryEventStore",
    "InMemoryOutboxStorage",
    "InMemoryRepository",
    "InMemoryUnitOfWork",
    "ILockStrategy",
    "InMemoryLockStrategy",
]
if HAS_GEO:
    __all__.append("SpatialMixin")
