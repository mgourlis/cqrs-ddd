"""MultitenantReplayMixin — sets tenant context per event during replay.

MRO composition mixin for ``ReplayEngine`` that extracts tenant_id from
each ``StoredEvent`` and sets the tenant context before dispatching to
projection handlers.

Usage::

    from cqrs_ddd_projections import ReplayEngine
    from cqrs_ddd_multitenancy.projections import MultitenantReplayMixin

    class TenantReplayEngine(MultitenantReplayMixin, ReplayEngine):
        pass
"""

from __future__ import annotations

import logging
from typing import Any

from ..context import clear_tenant, get_current_tenant_or_none, set_tenant
from .handler import extract_tenant_from_event

__all__ = [
    "MultitenantReplayMixin",
]

logger = logging.getLogger(__name__)


class MultitenantReplayMixin:
    """Mixin that wraps ``_dispatch_to_handlers`` to set tenant context
    per event during projection replay.

    Place this **before** ``ReplayEngine`` in the MRO::

        class TenantReplayEngine(MultitenantReplayMixin, ReplayEngine):
            pass

    For each event dispatched, the mixin:
    1. Extracts ``tenant_id`` from the stored event.
    2. Sets the tenant context.
    3. Delegates to ``super()._dispatch_to_handlers()``.
    4. Restores the previous tenant context.
    """

    async def _dispatch_to_handlers(self, stored: Any, domain_event: Any) -> None:
        """Set tenant context before dispatching to handlers."""
        tenant_id = extract_tenant_from_event(stored)
        if tenant_id is None:
            # Fall back to domain event metadata
            tenant_id = extract_tenant_from_event(domain_event)

        if tenant_id is None:
            await super()._dispatch_to_handlers(stored, domain_event)  # type: ignore[misc]
            return

        previous_tenant = get_current_tenant_or_none()
        token = set_tenant(tenant_id)
        try:
            await super()._dispatch_to_handlers(stored, domain_event)  # type: ignore[misc]
        finally:
            if previous_tenant is not None:
                set_tenant(previous_tenant)
            else:
                clear_tenant()
