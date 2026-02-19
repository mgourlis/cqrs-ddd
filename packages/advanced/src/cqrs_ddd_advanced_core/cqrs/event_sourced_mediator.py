"""EventSourcedMediator — extended Mediator with event persistence orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from cqrs_ddd_core.cqrs.event_dispatcher import EventDispatcher
    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.middleware.registry import MiddlewareRegistry
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from ..event_sourcing.persistence_orchestrator import (
        EventSourcedPersistenceOrchestrator,
    )


# Import core Mediator to extend it
from cqrs_ddd_core.cqrs.mediator import Mediator as CoreMediator


class EventSourcedMediator(CoreMediator):
    """Extended Mediator with mandatory, transactional event persistence.

    This class extends the core Mediator to add event persistence
    orchestration for event-sourced aggregates. All core Mediator
    functionality is preserved; this extension only adds persistence
    orchestration.

    **Architectural Role**
    - Drop-in replacement for core Mediator
    - Adds event persistence orchestration without modifying core package
    - Maintains all core Mediator behavior (middleware, UoW scope, etc.)

    **Event Persistence Flow**
    1. Mediator.send(command)
    2. Core Mediator creates UnitOfWork scope
    3. Command handler executes within UoW transaction
    4. Handler returns CommandResponse with events
    5. Core Mediator calls EventDispatcher (in-transaction handlers)
    6. **THIS EXTENSION:** EventSourcedPersistenceOrchestrator persists events
    7. UoW commits:
       - Aggregate state changes
       - EventStore records
       - Any other database changes

       OR rollback (if any step fails):
       - Everything rolls back together

    **Data Integrity Guarantee**
    Events are persisted in the SAME transaction as command execution.
    If command fails, events rollback. If persistence fails, command transaction
    fails. No events are lost or orphaned.

    **Example Configuration**
        ```python
        from cqrs_ddd_advanced_core.cqrs.event_sourced_mediator import (
            EventSourcedMediator,
        )
        from cqrs_ddd_advanced_core.event_sourcing.persistence_orchestrator import (
            EventSourcedPersistenceOrchestrator,
        )

        # Setup orchestrator
        orchestrator = EventSourcedPersistenceOrchestrator(event_store)
        orchestrator.register_event_sourced_type("Order")
        orchestrator.register_event_sourced_type("Invoice")

        # Configure Mediator (drop-in replacement)
        mediator = EventSourcedMediator(
            registry=handler_registry,
            uow_factory=uow_factory,
            event_dispatcher=event_dispatcher,
            event_persistence_orchestrator=orchestrator,
            middleware_registry=middleware_registry,
        )

        # Use exactly like core Mediator
        result = await mediator.send(CreateOrder(...))
        # ✓ Events persisted transactionally
        ```
    """

    def __init__(
        self,
        registry: Any,  # HandlerRegistry from core
        uow_factory: Callable[..., UnitOfWork],
        *,
        event_dispatcher: EventDispatcher[DomainEvent] | None = None,
        middleware_registry: MiddlewareRegistry | None = None,
        event_persistence_orchestrator: EventSourcedPersistenceOrchestrator
        | None = None,
        handler_factory: Callable[[type[Any]], Any] | None = None,
    ) -> None:
        """Initialize EventSourcedMediator.

        Args:
            registry: HandlerRegistry from core package.
            uow_factory: Callable that returns a UnitOfWork async-context-manager.
            event_dispatcher: Optional EventDispatcher for in-transaction handlers.
                If None, creates default dispatcher.
            middleware_registry: Optional MiddlewareRegistry for pipeline.
            event_persistence_orchestrator: Optional EventSourcedPersistenceOrchestrator
                for mandatory event persistence. If provided, events from
                event-sourced aggregates are persisted within UoW transaction.
            handler_factory: Optional callable for creating handler instances.
        """
        # Initialize core Mediator with all parameters except orchestrator
        # (we'll add persistence orchestration in _dispatch_command override)
        super().__init__(
            registry=registry,
            uow_factory=uow_factory,
            event_dispatcher=event_dispatcher,
            middleware_registry=middleware_registry,
            handler_factory=handler_factory,
        )

        self._event_persistence_orchestrator = event_persistence_orchestrator

    async def _dispatch_command(
        self,
        command: Any,
    ) -> Any:
        """Override core _dispatch_command to add event persistence.

        This method calls the parent's _dispatch_command, then adds
        event persistence orchestration for events from event-sourced
        aggregates. All within the same UnitOfWork transaction.
        """
        # Call parent's _dispatch_command (handles middleware, handlers, enrichment)
        result = await super()._dispatch_command(command)

        # MANDATORY: Persist events (if orchestrator configured)
        # This happens WITHIN the UoW transaction from send()
        # Events persist atomically with command execution
        if self._event_persistence_orchestrator and result.events:
            await self._event_persistence_orchestrator.persist_events(
                result.events, result
            )

        return result

    def configure_event_sourced_type(
        self,
        aggregate_type_name: str,
        event_store: Any = None,  # IEventStore
    ) -> None:
        """Convenience method to register an event-sourced aggregate type.

        Args:
            aggregate_type_name: Name of the aggregate class (e.g., "Order", "Invoice").
            event_store: Optional event store for this specific aggregate type.
                If None, uses the orchestrator's default store.

        Example:
            ```python
            mediator.configure_event_sourced_type("Order")
            mediator.configure_event_sourced_type("Invoice")
            ```
        """
        if self._event_persistence_orchestrator is None:
            from ..domain.exceptions import EventSourcingConfigurationError

            raise EventSourcingConfigurationError(
                "Cannot configure event-sourced types: "
                "event_persistence_orchestrator not provided"
            )

        self._event_persistence_orchestrator.register_event_sourced_type(
            aggregate_type_name,
            event_store=event_store,
        )

    def configure_non_event_sourced_type(self, aggregate_type_name: str) -> None:
        """Convenience method to register a non-event-sourced aggregate type.

        Args:
            aggregate_type_name: Name of the aggregate class.

        Example:
            ```python
            mediator.configure_non_event_sourced_type("CacheEntry")
            ```
        """
        if self._event_persistence_orchestrator is None:
            from ..domain.exceptions import EventSourcingConfigurationError

            raise EventSourcingConfigurationError(
                "Cannot configure non-event-sourced types: "
                "event_persistence_orchestrator not provided"
            )

        self._event_persistence_orchestrator.register_non_event_sourced_type(
            aggregate_type_name
        )
