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
    AggregateRoot,
    AuditableMixin,
    DomainEvent,
    EventTypeRegistry,
    Modification,
    ValueObject,
    enrich_event_metadata,
)

# ── Middleware ───────────────────────────────────────────────────
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

__all__ = [
    # Domain
    "AggregateRoot",
    "AuditableMixin",
    "DomainEvent",
    "EventTypeRegistry",
    "Modification",
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
