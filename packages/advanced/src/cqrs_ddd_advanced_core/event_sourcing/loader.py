"""EventSourcedLoader — load aggregates from snapshot + event store with upcasting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry

if TYPE_CHECKING:
    from collections.abc import Callable

    from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.ports.event_store import IEventStore

    from ..domain.event_validation import EventValidator
    from ..ports.event_applicator import IEventApplicator
    from ..ports.snapshots import ISnapshotStore
    from ..snapshots.strategy_registry import SnapshotStrategyRegistry
    from ..upcasting.registry import UpcasterRegistry


T = TypeVar("T", bound=AggregateRoot[Any])


class DefaultEventApplicator(Generic[T]):
    """
    Applies events by dispatching to apply_<EventTypeName>
    or apply_event on the aggregate.

    Now with optional runtime validation for better error messages.

    Args:
        validator: Optional EventValidator for handler validation.
                  If None, creates a default lenient validator.
        raise_on_missing_handler: If True, raise error when no handler exists.
                                  If False, silently ignore missing handlers.
                                  Defaults to True for safety.
    """

    def __init__(
        self,
        validator: EventValidator | None = None,
        *,
        raise_on_missing_handler: bool = True,
    ) -> None:
        # Import here to avoid circular dependency
        from ..domain.event_validation import EventValidationConfig, EventValidator

        self._validator = validator or EventValidator(
            EventValidationConfig(
                enabled=True, strict_mode=False, allow_fallback_handler=True
            )
        )
        self._raise_on_missing_handler = raise_on_missing_handler

    def apply(self, aggregate: T, event: DomainEvent) -> T:
        """Apply the event to the aggregate and return the aggregate.

        This method validates handler existence (if validation is enabled),
        then dispatches to the appropriate handler method.

        Args:
            aggregate: The aggregate instance to update.
            event: The domain event to apply.

        Returns:
            The same aggregate after applying the event (possibly mutated in place).

        Raises:
            MissingEventHandlerError: If no handler exists and validation is enabled.
            StrictValidationViolationError: If strict mode is violated.
            AttributeError: Legacy error for missing handlers (when validator disabled).
        """
        event_type = type(event).__name__

        # Validate handler exists (if validation enabled and we care about errors)
        # Skip validation if raise_on_missing_handler=False (silent mode)
        if self._raise_on_missing_handler:
            self._validator.validate_handler_exists(aggregate, event)

        # Try exact handler: apply_<EventType> or apply_<snake_case> (ruff-compliant)
        from ..domain.event_validation import event_type_to_snake

        method = getattr(aggregate, f"apply_{event_type}", None)
        if method is None or not callable(method):
            method = getattr(
                aggregate, f"apply_{event_type_to_snake(event_type)}", None
            )
        if method is not None and callable(method):
            method(event)
            return aggregate

        # Try fallback handler: apply_event
        method = getattr(aggregate, "apply_event", None)
        if method is not None and callable(method):
            method(event)
            return aggregate

        # No handler found
        if self._raise_on_missing_handler:
            # Try to use custom exception if validation was enabled
            if self._validator.is_enabled():
                from ..domain.exceptions import MissingEventHandlerError

                raise MissingEventHandlerError(
                    aggregate_type=type(aggregate).__name__,
                    event_type=event_type,
                )
            # Legacy error message for backward compatibility
            raise AttributeError(
                f"Aggregate {type(aggregate).__name__} "
                f"has no apply_{event_type} or apply_event"
            )

        # Silently ignore if configured
        return aggregate


class EventSourcedLoader(Generic[T]):
    """
    Loads event-sourced aggregates from snapshot (if any) + event store, with upcasting.

    **Flow:** get_latest_snapshot → restore or create fresh → get_events(after_version)
    → upcast each payload → hydrate to DomainEvent → apply to aggregate.
    """

    def __init__(
        self,
        aggregate_type: type[T],
        event_store: IEventStore,
        event_registry: EventTypeRegistry,
        *,
        snapshot_store: ISnapshotStore | None = None,
        upcaster_registry: UpcasterRegistry | None = None,
        snapshot_strategy_registry: SnapshotStrategyRegistry | None = None,
        applicator: IEventApplicator[T] | None = None,
        create_aggregate: Callable[[str], T] | None = None,
    ) -> None:
        self._aggregate_type = aggregate_type
        self._event_store = event_store
        self._event_registry = event_registry
        self._snapshot_store = snapshot_store
        self._upcaster_registry = upcaster_registry
        self._snapshot_strategy_registry = snapshot_strategy_registry
        self._applicator = applicator or DefaultEventApplicator[T]()
        self._create_aggregate = create_aggregate or (
            lambda aid: aggregate_type(id=aid)
        )
        self._aggregate_type_name = aggregate_type.__name__

    async def load(self, aggregate_id: str) -> T | None:
        """Reconstitute an aggregate from snapshot (if any) and events.

        1. Try snapshot_store.get_latest_snapshot()
        2. Restore aggregate from snapshot or create fresh
        3. Load events from event_store.get_events(aggregate_id, after_version=...)
        4. Upcast each payload if upcaster_registry has upcasters
        5. Hydrate to DomainEvent via event_registry
        6. Apply each event to the aggregate
        7. Return the reconstituted aggregate, or None if no snapshot and no events
        """
        after_version = 0
        aggregate: T | None = None

        if self._snapshot_store:
            snapshot = await self._snapshot_store.get_latest_snapshot(
                self._aggregate_type_name, aggregate_id
            )
            if snapshot:
                snapshot_data = snapshot.get("snapshot_data") or snapshot
                version = snapshot.get("version", 0)
                aggregate = self._aggregate_type.model_validate(snapshot_data)
                object.__setattr__(aggregate, "_version", version)
                after_version = version

        if aggregate is None:
            try:
                aggregate = self._create_aggregate(aggregate_id)
            except Exception:  # noqa: BLE001
                return None
            object.__setattr__(aggregate, "_version", 0)

        raw_events = await self._event_store.get_events(
            aggregate_id, after_version=after_version
        )
        if not raw_events and after_version == 0:
            # No snapshot and no events: aggregate never existed
            return None

        for stored_event in raw_events:
            payload = dict(stored_event.payload)
            schema_ver = getattr(stored_event, "schema_version", 1)

            if self._upcaster_registry and self._upcaster_registry.has_upcasters(
                stored_event.event_type
            ):
                payload, schema_ver = self._upcaster_registry.upcast(
                    stored_event.event_type, payload, schema_ver
                )

            domain_event = self._event_registry.hydrate(
                stored_event.event_type, payload
            )
            if domain_event is None:
                continue
            aggregate = self._applicator.apply(aggregate, domain_event)
            object.__setattr__(aggregate, "_version", stored_event.version)

        return aggregate

    async def maybe_snapshot(self, aggregate: T) -> None:
        """If a snapshot strategy says so, save a snapshot for this aggregate."""
        if not self._snapshot_store:
            return
        if not self._snapshot_strategy_registry:
            return
        if not self._snapshot_strategy_registry.should_snapshot(
            self._aggregate_type_name, aggregate
        ):
            return
        snapshot_data = aggregate.model_dump(mode="json")
        version = aggregate.version
        agg_id = getattr(aggregate, "id", None)
        if agg_id is None:
            return
        await self._snapshot_store.save_snapshot(
            self._aggregate_type_name, agg_id, snapshot_data, version
        )
