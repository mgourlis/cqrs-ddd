"""EventSourcedPersistenceOrchestrator — transactional event persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.ports.event_store import IEventStore


class EventSourcedPersistenceOrchestrator:
    """Orchestrates mandatory, transactional event persistence for
    event-sourced aggregates.

    **CRITICAL: Data Integrity Guarantee**
    All events from event-sourced aggregates are persisted in the SAME
    transaction as the command execution. If the command fails, events
    rollback. If persistence
    fails, the command transaction fails. No events are lost or orphaned.

    **Architectural Role**
    - Works within UnitOfWork transaction scope
    - Persists events before UoW commit
    - Fail-fast if event-sourced aggregate not registered

    **Integration with Mediator**
    Mediator calls orchestrator.persist_events() within UoW transaction:

        ```python
        async def _dispatch_command(self, command):
            async with self._uow_factory() as uow:
                result = await pipeline(command)

                # Stage 1: Dispatch handlers (in-transaction)
                await self._event_dispatcher.dispatch(result.events)

                # Stage 2: Persist events (MANDATORY, in-transaction)
                # This MUST succeed or entire transaction fails
                await self._event_persistence_orchestrator.persist_events(
                    result.events, result
                )

                # UoW commits: aggregate state + events together
                # Or rolls back: everything together
        ```

    **Selective Persistence**
    - Event-sourced aggregates: Events MUST be persisted (mandatory)
    - Non-event-sourced aggregates: Events are NOT persisted
    - Configuration is explicit (no accidental data loss)

    **Example Configuration**
        ```python
        # Setup
        orchestrator = EventSourcedPersistenceOrchestrator(event_store)

        # Register event-sourced aggregates (MUST persist events)
        orchestrator.register_event_sourced_type("Order")
        orchestrator.register_event_sourced_type("Invoice")

        # Non-event-sourced aggregates (optional - events not persisted)
        # CacheEntry, AuditLog, etc. are NOT registered
        ```
    """

    def __init__(
        self,
        default_event_store: IEventStore,
        *,
        enforce_registration: bool = True,
    ) -> None:
        """Initialize orchestrator.

        Args:
            default_event_store: Default EventStore for event-sourced aggregates.
                REQUIRED for transactional integrity. Events persisted atomically
                with command execution.
            enforce_registration: If True (default), raises when unregistered
                aggregate types produce events. Prevents accidental data loss.
        """
        if default_event_store is None:
            from ..domain.exceptions import EventSourcingConfigurationError

            raise EventSourcingConfigurationError(
                "EventSourcedPersistenceOrchestrator requires default_event_store "
                "for transactional integrity. Events must be persisted atomically "
                "with command execution."
            )

        self._default_event_store = default_event_store
        self._event_sourced_types: set[str] = set()
        self._non_event_sourced_types: set[str] = set()
        self._aggregate_stores: dict[str, IEventStore] = {}
        self._enforce_registration = enforce_registration

    def register_event_sourced_type(
        self,
        aggregate_type_name: str,
        event_store: IEventStore | None = None,
    ) -> None:
        """Register an aggregate type as event-sourced (events MUST be persisted).

        **Data Integrity**: Events from this aggregate type will always be
        persisted in the same transaction as command execution. If persistence
        fails, the command transaction fails.

        Args:
            aggregate_type_name: Name of the aggregate class (e.g., "Order", "Invoice").
            event_store: Optional event store for this specific aggregate type.
                If None, uses default_event_store.

        Raises:
            ValueError: If neither event_store nor default_event_store is configured.

        Example:
            ```python
            # Use default event store
            orchestrator.register_event_sourced_type("Order")

            # Use specific event store (e.g., separate database)
            orchestrator.register_event_sourced_type(
                "Invoice", event_store=invoice_store
            )
            ```
        """
        store = event_store or self._default_event_store
        if store is None:
            from ..domain.exceptions import EventSourcingConfigurationError

            raise EventSourcingConfigurationError(
                f"Cannot register {aggregate_type_name} as event-sourced: "
                "no event_store available"
            )

        self._event_sourced_types.add(aggregate_type_name)
        if event_store is not None:
            self._aggregate_stores[aggregate_type_name] = event_store

    def register_non_event_sourced_type(self, aggregate_type_name: str) -> None:
        """Register an aggregate type as non-event-sourced (events NOT persisted).

        This is optional but provides explicit configuration for aggregates that
        produce events but don't require event store persistence.

        Args:
            aggregate_type_name: Name of the aggregate class.

        Example:
            ```python
            # Cache aggregates produce events but don't need persistence
            orchestrator.register_non_event_sourced_type("CacheEntry")
            ```
        """
        self._non_event_sourced_types.add(aggregate_type_name)

    def is_event_sourced(self, aggregate_type: str) -> bool:
        """Check if an aggregate type is registered as event-sourced.

        Args:
            aggregate_type: Name of the aggregate type.

        Returns:
            True if the aggregate type is event-sourced, False otherwise.

        Example:
            ```python
            if orchestrator.is_event_sourced("Order"):
                # This aggregate's events should be persisted
                pass
            ```
        """
        return aggregate_type in self._event_sourced_types

    def get_event_store(self, aggregate_type: str) -> IEventStore:
        """Get event store for a specific aggregate type.

        Args:
            aggregate_type: Name of the aggregate type.

        Returns:
            The event store configured for this aggregate type.

        Raises:
            ValueError: If the aggregate type is not event-sourced.

        Example:
            ```python
            store = orchestrator.get_event_store("Order")
            if store:
                # Persist event
                await store.append(stored_event)
            ```
        """
        if not self.is_event_sourced(aggregate_type):
            from ..domain.exceptions import EventSourcingConfigurationError

            raise EventSourcingConfigurationError(
                f"Aggregate type '{aggregate_type}' is not registered as event-sourced"
            )

        return self._aggregate_stores.get(aggregate_type) or self._default_event_store

    async def persist_event(
        self,
        event: DomainEvent,
        command_response: Any,
    ) -> None:
        """Persist a single event (MUST be called within UoW transaction).

        **Transactional Guarantee**: This method MUST be called within the same
        UnitOfWork transaction as the command execution. The transaction will
        commit or rollback atomically.

        Args:
            event: The domain event to persist.
            command_response: The command response containing metadata
                (correlation_id, causation_id, etc.).

        Raises:
            EventSourcedAggregateRequiredError: If the aggregate type
                produces events but is not registered as event-sourced (only when
                enforce_registration=True).

        Example:
            ```python
            # Within UoW transaction
            async with uow_factory() as uow:
                result = await handler.handle(command)
                await orchestrator.persist_events(result.events, result)
                # uow.__aexit__ commits both aggregate state and events
            ```
        """

        aggregate_type = getattr(event, "aggregate_type", None)
        if not aggregate_type:
            return  # Skip events without aggregate type

        # Check if aggregate is event-sourced
        if not self.is_event_sourced(aggregate_type):
            if aggregate_type in self._non_event_sourced_types:
                # Explicitly registered as non-event-sourced - skip
                return

            # Unknown aggregate type that produces events
            if self._enforce_registration:
                from ..domain.exceptions import EventSourcedAggregateRequiredError

                raise EventSourcedAggregateRequiredError(aggregate_type)

            # Lenient mode - skip without persistence
            return

        store = self.get_event_store(aggregate_type)
        stored_event = self._create_stored_event(event, command_response)
        await store.append(stored_event)

    async def persist_events(
        self,
        events: list[DomainEvent],
        command_response: Any,
    ) -> None:
        """Persist multiple events (MUST be called within UoW transaction).

        **Transactional Guarantee**: All events are persisted in the same transaction.
        If any event persistence fails, the entire transaction fails.

        Args:
            events: List of domain events.
            command_response: The command response containing metadata.

        Raises:
            EventSourcedAggregateRequiredError: If any event's aggregate type
                produces events but is not registered as event-sourced.

        Example:
            ```python
            # Mediator calls this within UoW transaction
            async with self._uow_factory() as uow:
                result = await self._dispatch_command(command)

                # Dispatch handlers (in-transaction)
                await self._event_dispatcher.dispatch(result.events)

                # Persist events (MANDATORY, in-transaction)
                await self._event_persistence_orchestrator.persist_events(
                    result.events, result
                )

                # Transaction commits or rolls back atomically
            ```
        """
        registry = get_hook_registry()
        await registry.execute_all(
            "persistence_orchestrator.orchestrate",
            {
                "event_count": len(events),
                "correlation_id": get_correlation_id()
                or getattr(command_response, "correlation_id", None),
            },
            lambda: self._persist_events_internal(events, command_response),
        )

    async def _persist_events_internal(
        self,
        events: list[DomainEvent],
        command_response: Any,
    ) -> None:
        for event in events:
            await self.persist_event(event, command_response)

    def _create_stored_event(
        self,
        event: DomainEvent,
        command_response: Any,
    ) -> Any:
        """Create a StoredEvent from a domain event.

        Args:
            event: The domain event.
            command_response: The command response for metadata.

        Returns:
            A StoredEvent instance.
        """
        from cqrs_ddd_core.ports.event_store import StoredEvent

        # Calculate event sequence number
        result_payload = getattr(command_response, "result", None)
        entity = getattr(result_payload, "entity", None) if result_payload else None
        base_version = (
            getattr(entity, "version", 0) - len(command_response.events)
            if entity
            else 0
        )
        event_index = (
            list(command_response.events).index(event)
            if event in command_response.events
            else 0
        )

        return StoredEvent(
            event_id=getattr(event, "event_id", ""),
            event_type=type(event).__name__,
            aggregate_id=str(getattr(event, "aggregate_id", "")),
            aggregate_type=getattr(event, "aggregate_type", ""),
            version=base_version + event_index + 1,
            schema_version=getattr(event, "version", 1),
            payload=event.model_dump(),
            metadata=getattr(event, "metadata", {}),
            occurred_at=getattr(event, "occurred_at", None)
            or datetime.now(timezone.utc),
            correlation_id=getattr(command_response, "correlation_id", None),
            causation_id=getattr(command_response, "causation_id", None),
        )

    def unregister_event_sourced_type(self, aggregate_type_name: str) -> None:
        """Unregister an aggregate type as event-sourced.

        Args:
            aggregate_type_name: Name of the aggregate type.

        Example:
            ```python
            # Temporarily disable event sourcing for testing
            orchestrator.unregister_event_sourced_type("Order")
            ```
        """
        self._event_sourced_types.discard(aggregate_type_name)
        self._aggregate_stores.pop(aggregate_type_name, None)

    def clear_registrations(self) -> None:
        """Clear all aggregate type registrations (testing utility).

        Example:
            ```python
            # Between tests
            orchestrator.clear_registrations()
            ```
        """
        self._event_sourced_types.clear()
        self._aggregate_stores.clear()
