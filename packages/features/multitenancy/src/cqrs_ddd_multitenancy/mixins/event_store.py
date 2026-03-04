"""Multitenant event store mixin for tenant-scoped event storage.

This mixin adds tenant_id filtering to all event store operations,
ensuring events are properly isolated by tenant using a DEDICATED COLUMN
(not JSONB metadata) for optimal database-level filtering.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from ..context import get_current_tenant_or_none, is_system_tenant
from ..exceptions import TenantContextMissingError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from cqrs_ddd_core.ports.event_store import StoredEvent

__all__ = [
    "MultitenantEventStoreMixin",
]

logger = logging.getLogger(__name__)


class MultitenantEventStoreMixin:
    """Mixin that adds specification-based tenant filtering to event store operations.

    This mixin intercepts all event store methods to inject and filter
    by tenant_id using specifications. It should be used via MRO composition:

        class MyEventStore(MultitenantEventStoreMixin, SQLAlchemyEventStore):
            pass

    Key behaviors:
    - **append()**: Injects tenant_id into event.tenant_id field
    - **append_batch()**: Injects tenant_id into all events
    - **get_events()**: Composes tenant specification with query
    - **get_by_aggregate()**: Composes tenant specification with query
    - **get_all()**: Evaluates tenant specification at DB level
    - **get_events_after()**: Composes tenant specification with query

    How specifications work:
        1. Mixin creates an AttributeSpecification for tenant_id
        2. Implementation evaluates specification at database level
        3. SQLAlchemy: WHERE tenant_id = ?
        4. MongoDB: {tenant_id: '...'}
        5. In-memory: Filter Python objects

    The tenant_id is stored in a dedicated column (not JSONB metadata) for:
    - B-tree index performance
    - Row-Level Security (RLS) support
    - Foreign key constraints
    - Table partitioning

    Note:
        The mixin uses super() to call the next class in MRO, so it must
        be placed before the base event store class.
    """

    def _build_tenant_specification(self, tenant_id: str) -> Any:
        """Build a tenant specification for database queries.

        Args:
            tenant_id: The tenant ID to filter by.

        Returns:
            An ISpecification that filters by tenant_id.
        """
        try:
            from cqrs_ddd_specifications import AttributeSpecification
            from cqrs_ddd_specifications.operators import SpecificationOperator
            from cqrs_ddd_specifications.operators_memory import build_default_registry

            return AttributeSpecification(
                attr="tenant_id",
                op=SpecificationOperator.EQ,
                val=tenant_id,
                registry=build_default_registry(),
            )
        except ImportError:
            # Fallback to dict-based specification
            return {"attr": "tenant_id", "op": "eq", "value": tenant_id}

    def _compose_specs(self, tenant_spec: Any, other: Any | None) -> Any:
        """Compose tenant specification with an optional additional specification.

        Args:
            tenant_spec: The tenant specification.
            other: Optional additional specification to compose with.

        Returns:
            The composed specification, or just tenant_spec if other is None.
        """
        if other is None:
            return tenant_spec
        if hasattr(tenant_spec, "__and__") and hasattr(other, "__and__"):
            try:
                return tenant_spec & other
            except (TypeError, AttributeError):
                pass
        return tenant_spec

    def _require_tenant_context(self) -> str:
        """Require and return the current tenant ID.

        Returns:
            The current tenant ID.

        Raises:
            TenantContextMissingError: If no tenant context is set.
        """
        tenant = get_current_tenant_or_none()
        if tenant is None and not is_system_tenant():
            raise TenantContextMissingError(
                "Tenant context required for event store operation. "
                "Ensure TenantMiddleware is configured or use @system_operation."
            )
        return tenant or "__system__"

    def _inject_tenant_into_event(
        self, event: StoredEvent, tenant_id: str
    ) -> StoredEvent:
        """Inject tenant_id into event.tenant_id field.

        Uses dataclasses.replace to create a new StoredEvent with tenant_id set.

        Args:
            event: The original stored event.
            tenant_id: The tenant ID to inject.

        Returns:
            A new StoredEvent with tenant_id field set.
        """
        # Use dataclasses.replace for frozen dataclass
        if dataclasses.is_dataclass(event):
            return dataclasses.replace(event, tenant_id=tenant_id)

        # Fallback: try to create new instance
        return event.__class__(
            event_id=event.event_id,
            event_type=event.event_type,
            aggregate_id=event.aggregate_id,
            aggregate_type=event.aggregate_type,
            version=event.version,
            schema_version=event.schema_version,
            payload=event.payload,
            metadata=event.metadata,
            occurred_at=event.occurred_at,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            position=event.position,
            tenant_id=tenant_id,
        )

    # Note: In-memory filtering removed - database MUST filter at query level

    # -----------------------------------------------------------------------
    # Event store method overrides
    # -----------------------------------------------------------------------

    async def append(self: Any, stored_event: StoredEvent) -> None:
        """Append event with tenant_id injection.

        Args:
            stored_event: The event to append.

        Raises:
            TenantContextMissingError: If no tenant context.
        """
        if is_system_tenant():
            return await super().append(stored_event)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        event_with_tenant = self._inject_tenant_into_event(stored_event, tenant_id)

        logger.debug(
            "Appending event with tenant",
            extra={
                "tenant_id": tenant_id,
                "event_type": stored_event.event_type,
                "aggregate_id": stored_event.aggregate_id,
            },
        )

        return await super().append(event_with_tenant)  # type: ignore[misc, no-any-return]

    async def append_batch(self: Any, events: list[StoredEvent]) -> None:
        """Append events with tenant_id injection.

        Args:
            events: The events to append.

        Raises:
            TenantContextMissingError: If no tenant context.
        """
        if is_system_tenant():
            return await super().append_batch(events)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        events_with_tenant = [
            self._inject_tenant_into_event(event, tenant_id) for event in events
        ]

        logger.debug(
            "Appending event batch with tenant",
            extra={
                "tenant_id": tenant_id,
                "event_count": len(events),
            },
        )

        return await super().append_batch(events_with_tenant)  # type: ignore[misc, no-any-return]

    async def get_events(
        self: Any,
        aggregate_id: str,
        *,
        after_version: int = 0,
        specification: Any | None = None,
    ) -> list[StoredEvent]:
        """Get events for aggregate with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            aggregate_id: The aggregate ID.
            after_version: Minimum version (exclusive).
            specification: Optional additional specification to compose with.

        Returns:
            List of events filtered by tenant (via specification).
        """
        if is_system_tenant():
            return await super().get_events(  # type: ignore[misc, no-any-return]
                aggregate_id, after_version=after_version, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Getting events with tenant specification",
            extra={"tenant_id": tenant_id, "aggregate_id": aggregate_id},
        )

        return await super().get_events(  # type: ignore[misc, no-any-return]
            aggregate_id, after_version=after_version, specification=combined
        )

    async def get_by_aggregate(
        self: Any,
        aggregate_id: str,
        aggregate_type: str | None = None,
        *,
        specification: Any | None = None,
    ) -> list[StoredEvent]:
        """Get all events for aggregate with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            aggregate_id: The aggregate ID.
            aggregate_type: Optional aggregate type filter.
            specification: Optional additional specification to compose with.

        Returns:
            List of events filtered by tenant (via specification).
        """
        if is_system_tenant():
            return await super().get_by_aggregate(  # type: ignore[misc, no-any-return]
                aggregate_id, aggregate_type, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Getting events by aggregate with tenant specification",
            extra={"tenant_id": tenant_id, "aggregate_id": aggregate_id},
        )

        return await super().get_by_aggregate(  # type: ignore[misc, no-any-return]
            aggregate_id, aggregate_type, specification=combined
        )

    async def get_all(
        self: Any,
        *,
        specification: Any | None = None,
    ) -> list[StoredEvent]:
        """Get all events with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            specification: Optional additional specification to compose with.

        Returns:
            List of events filtered by tenant (via specification).

        Raises:
            TenantContextMissingError: If no tenant context.
        """
        if is_system_tenant():
            return await super().get_all(specification=specification)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Getting all events with tenant specification",
            extra={"tenant_id": tenant_id},
        )

        return await super().get_all(specification=combined)  # type: ignore[misc, no-any-return]

    async def get_events_after(
        self: Any,
        position: int,
        limit: int = 1000,
        *,
        specification: Any | None = None,
    ) -> list[StoredEvent]:
        """Get events after position with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            position: The starting position (exclusive).
            limit: Maximum number of events to return.
            specification: Optional additional specification to compose with.

        Returns:
            List of events filtered by tenant (via specification).
        """
        if is_system_tenant():
            return await super().get_events_after(  # type: ignore[misc, no-any-return]
                position, limit, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Getting events after position with tenant specification",
            extra={"tenant_id": tenant_id, "position": position},
        )

        return await super().get_events_after(position, limit, specification=combined)  # type: ignore[misc, no-any-return]

    async def stream_all(
        self: Any,
        batch_size: int = 1000,
        *,
        specification: Any | None = None,
    ) -> AsyncIterator[StoredEvent]:
        """Stream all events with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            batch_size: Number of events per batch.
            specification: Optional additional specification to compose with.

        Yields:
            Events filtered by tenant (via specification).
        """
        if is_system_tenant():
            async for event in super().stream_all(  # type: ignore[misc]
                batch_size, specification=specification
            ):
                yield event
            return

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Streaming all events with tenant specification",
            extra={"tenant_id": tenant_id},
        )

        async for event in super().stream_all(batch_size, specification=combined):  # type: ignore[misc]
            yield event

    def get_events_from_position(
        self: Any,
        position: int,
        *,
        limit: int | None = None,
        specification: Any | None = None,
    ) -> AsyncIterator[StoredEvent]:
        """Stream events from position with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            position: Starting position (exclusive).
            limit: Optional batch size limit per internal batch.
            specification: Optional additional specification to compose with.

        Yields:
            StoredEvent objects filtered by tenant.
        """
        if is_system_tenant():
            return super().get_events_from_position(  # type: ignore[misc, no-any-return]
                position, limit=limit, specification=specification
            )

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Streaming events from position with tenant specification",
            extra={"tenant_id": tenant_id, "position": position},
        )

        return super().get_events_from_position(  # type: ignore[misc, no-any-return]
            position, limit=limit, specification=combined
        )

    def get_all_streaming(
        self: Any,
        batch_size: int = 1000,
        *,
        specification: Any | None = None,
    ) -> AsyncIterator[list[StoredEvent]]:
        """Stream all events in batches with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            batch_size: Number of events per batch.
            specification: Optional additional specification to compose with.

        Yields:
            Lists of StoredEvent objects filtered by tenant.
        """
        if is_system_tenant():
            return super().get_all_streaming(batch_size, specification=specification)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Streaming all events in batches with tenant specification",
            extra={"tenant_id": tenant_id},
        )

        return super().get_all_streaming(batch_size, specification=combined)  # type: ignore[misc, no-any-return]

    async def get_latest_position(
        self: Any,
        *,
        specification: Any | None = None,
    ) -> int | None:
        """Get latest position with specification-based tenant filtering.

        Creates a tenant specification and passes it via the specification
        parameter for evaluation at the database level.

        Args:
            specification: Optional additional specification to compose with.

        Returns:
            The highest position value for this tenant, or None.
        """
        if is_system_tenant():
            return await super().get_latest_position(specification=specification)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        combined = self._compose_specs(tenant_spec, specification)

        logger.debug(
            "Getting latest position with tenant specification",
            extra={"tenant_id": tenant_id},
        )

        return await super().get_latest_position(specification=combined)  # type: ignore[misc, no-any-return]
