"""MultitenantWorkerMixin — sets tenant context per event in ProjectionWorker.

MRO composition mixin for ``ProjectionWorker`` that extracts tenant_id from
each ``StoredEvent`` and sets the tenant context before dispatching to
projection handlers.

Usage::

    from cqrs_ddd_projections import ProjectionWorker
    from cqrs_ddd_multitenancy.projections import MultitenantWorkerMixin

    class TenantProjectionWorker(MultitenantWorkerMixin, ProjectionWorker):
        pass
"""

from __future__ import annotations

import logging
from typing import Any

from ..context import clear_tenant, get_current_tenant_or_none, set_tenant
from .handler import extract_tenant_from_event

__all__ = [
    "MultitenantWorkerMixin",
]

logger = logging.getLogger(__name__)


class MultitenantWorkerMixin:
    """Mixin that wraps ``_dispatch`` to set tenant context per event
    during projection worker processing.

    Place this **before** ``ProjectionWorker`` in the MRO::

        class TenantProjectionWorker(MultitenantWorkerMixin, ProjectionWorker):
            pass

    For each event dispatched, the mixin:
    1. Extracts ``tenant_id`` from the stored event.
    2. Sets the tenant context.
    3. Delegates to ``super()._dispatch()``.
    4. Restores the previous tenant context.
    """

    async def _dispatch(
        self, event: Any, stored: Any, event_position: int, retry_count: int
    ) -> None:
        """Set tenant context before dispatching to handlers."""
        tenant_id = extract_tenant_from_event(stored)
        if tenant_id is None:
            tenant_id = extract_tenant_from_event(event)

        if tenant_id is None:
            await super()._dispatch(event, stored, event_position, retry_count)  # type: ignore[misc]
            return

        previous_tenant = get_current_tenant_or_none()
        token = set_tenant(tenant_id)
        try:
            await super()._dispatch(event, stored, event_position, retry_count)  # type: ignore[misc]
        finally:
            if previous_tenant is not None:
                set_tenant(previous_tenant)
            else:
                clear_tenant()
