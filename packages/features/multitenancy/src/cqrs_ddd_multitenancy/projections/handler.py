"""MultitenantProjectionHandler — tenant-aware projection handler wrapper.

Wraps any ``IProjectionHandler`` to extract tenant context from the event
(via ``metadata['tenant_id']`` or a dedicated ``tenant_id`` attribute) and
set the tenant context before delegating to the inner handler.

Usage::

    from cqrs_ddd_projections import ProjectionHandler
    from cqrs_ddd_multitenancy.projections import MultitenantProjectionHandler

    # Wrap an existing handler
    handler = MyOrderProjection()
    tenant_handler = MultitenantProjectionHandler(handler)
    # Now handler.handle(event) sets tenant context automatically.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..context import (
    SYSTEM_TENANT,
    clear_tenant,
    get_current_tenant_or_none,
    set_tenant,
)

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent

__all__ = [
    "MultitenantProjectionHandler",
    "extract_tenant_from_event",
]

logger = logging.getLogger(__name__)


def extract_tenant_from_event(event: Any) -> str | None:
    """Extract tenant_id from a domain event or stored event.

    Checks (in order):
    1. ``event.tenant_id`` (dedicated attribute on ``StoredEvent``)
    2. ``event.metadata.get('tenant_id')``

    Returns:
        The tenant ID, or ``None`` if not present.
    """
    # Dedicated attribute (StoredEvent, MultitenantMixin aggregates)
    tenant_id = getattr(event, "tenant_id", None)
    if tenant_id is not None:
        return str(tenant_id)

    # Metadata dict (DomainEvent.metadata)
    metadata = getattr(event, "metadata", None)
    if isinstance(metadata, dict):
        tid = metadata.get("tenant_id")
        if tid is not None:
            return str(tid)

    return None


class MultitenantProjectionHandler:
    """Wraps an ``IProjectionHandler`` to set tenant context from the event.

    When ``handle(event)`` is called:
    1. Extracts ``tenant_id`` from the event.
    2. Sets the tenant context (``set_tenant()``).
    3. Delegates to the inner handler.
    4. Restores the previous tenant context.

    If no tenant_id is found on the event, the handler executes without
    changing the tenant context (preserves caller's context).

    Args:
        inner: The wrapped projection handler.
        tenant_column: Metadata key to read the tenant ID from.
            Defaults to ``"tenant_id"``.
        skip_system_events: If ``True``, events with SYSTEM_TENANT
            are dispatched but without changing context.
    """

    def __init__(
        self,
        inner: Any,
        *,
        tenant_column: str = "tenant_id",
        skip_system_events: bool = True,
    ) -> None:
        self._inner = inner
        self._tenant_column = tenant_column
        self._skip_system_events = skip_system_events

    @property
    def handles(self) -> set[type[DomainEvent]]:
        """Delegate to inner handler's ``handles`` property."""
        return self._inner.handles  # type: ignore[no-any-return]

    async def handle(self, event: DomainEvent) -> None:
        """Set tenant context from event, then delegate to inner handler."""
        tenant_id = self._extract_tenant(event)

        if tenant_id is None:
            # No tenant info — delegate without changing context
            await self._inner.handle(event)
            return

        if self._skip_system_events and tenant_id == SYSTEM_TENANT:
            # System events run without tenant isolation
            await self._inner.handle(event)
            return

        # Save and restore tenant context
        previous_tenant = get_current_tenant_or_none()
        token = set_tenant(tenant_id)
        try:
            await self._inner.handle(event)
        finally:
            if previous_tenant is not None:
                set_tenant(previous_tenant)
            else:
                clear_tenant()

    def _extract_tenant(self, event: Any) -> str | None:
        """Extract tenant from event using configured column name."""
        # Dedicated attribute
        tenant_id = getattr(event, self._tenant_column, None)
        if tenant_id is not None:
            return str(tenant_id)

        # Metadata dict
        metadata = getattr(event, "metadata", None)
        if isinstance(metadata, dict):
            tid = metadata.get(self._tenant_column)
            if tid is not None:
                return str(tid)

        return None
