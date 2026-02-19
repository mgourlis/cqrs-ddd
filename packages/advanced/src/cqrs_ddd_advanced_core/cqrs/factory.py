"""EventSourcedMediatorFactory — factory for creating configured mediators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..event_sourcing.persistence_orchestrator import (
    EventSourcedPersistenceOrchestrator,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from cqrs_ddd_core.ports.event_store import IEventStore
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from .event_sourced_mediator import EventSourcedMediator


class EventSourcedMediatorFactory:
    """Factory for creating pre-configured EventSourcedMediator instances.

    Simplifies the setup of EventSourcedMediator with commonly used
    configurations for event-sourced aggregates.

    **Example**
        ```python
        factory = EventSourcedMediatorFactory(
            event_store=event_store,
            uow_factory=uow_factory,
            handler_registry=handler_registry,
            event_dispatcher=event_dispatcher,
        )

        # Configure event-sourced aggregates
        factory.register_event_sourced_type("Order")
        factory.register_event_sourced_type("Invoice")

        # Create mediator (ready to use)
        mediator = factory.create()
        ```
    """

    def __init__(
        self,
        event_store: IEventStore,
        uow_factory: Callable[..., UnitOfWork],
        handler_registry: Any,
        event_dispatcher: Any = None,
        middleware_registry: Any = None,
        handler_factory: Callable[[type[Any]], Any] | None = None,
        *,
        enforce_registration: bool = True,
    ) -> None:
        """Initialize factory.

        Args:
            event_store: Default EventStore for all event-sourced aggregates.
                This is REQUIRED for transactional integrity. Events must be
                persisted atomically with command execution.
            uow_factory: UnitOfWork factory.
            handler_registry: HandlerRegistry from core package.
            event_dispatcher: Optional EventDispatcher.
            middleware_registry: Optional MiddlewareRegistry.
            handler_factory: Optional handler factory function.
            enforce_registration: If True (default), orchestrator raises error for
                unregistered aggregates that produce events.
        """
        self._orchestrator = EventSourcedPersistenceOrchestrator(
            default_event_store=event_store,
            enforce_registration=enforce_registration,
        )
        self._uow_factory = uow_factory
        self._handler_registry = handler_registry
        self._event_dispatcher = event_dispatcher
        self._middleware_registry = middleware_registry
        self._handler_factory = handler_factory

    def register_event_sourced_type(
        self,
        aggregate_type_name: str,
        event_store: IEventStore | None = None,
    ) -> None:
        """Register an aggregate type as event-sourced."""
        self._orchestrator.register_event_sourced_type(
            aggregate_type_name,
            event_store=event_store,
        )

    def register_non_event_sourced_type(self, aggregate_type_name: str) -> None:
        """Register an aggregate type as non-event-sourced."""
        self._orchestrator.register_non_event_sourced_type(aggregate_type_name)

    def create(self) -> EventSourcedMediator:
        """Create a fully configured EventSourcedMediator.

        Returns:
            EventSourcedMediator instance ready to use.
        """
        from .event_sourced_mediator import EventSourcedMediator

        return EventSourcedMediator(
            registry=self._handler_registry,
            uow_factory=self._uow_factory,
            event_dispatcher=self._event_dispatcher,
            middleware_registry=self._middleware_registry,
            event_persistence_orchestrator=self._orchestrator,
            handler_factory=self._handler_factory,
        )
