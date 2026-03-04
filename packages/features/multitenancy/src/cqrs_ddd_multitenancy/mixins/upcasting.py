"""Multitenant event upcaster mixin for preserving tenant context.

This mixin ensures that tenant_id is preserved through event upcasting
transformations when composed with a base upcaster class via MRO.

Usage:
    class MyEventUpcaster(MultitenantUpcasterMixin, OrderCreatedUpcaster):
        pass

The mixin must appear BEFORE the base upcaster in the MRO to ensure
method resolution overrides the base methods correctly.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = [
    "MultitenantUpcasterMixin",
]

logger = logging.getLogger(__name__)


class MultitenantUpcasterMixin:
    """Mixin that preserves tenant context during event upcasting.

    This mixin wraps event upcasting to ensure tenant_id is never
    lost or corrupted during schema migrations. It should be used via MRO:

        class MyUpcaster(MultitenantUpcasterMixin, OrderCreatedUpcaster):
            pass

    Key behaviors:
    - **upcast()**: Extracts tenant_id before transformation, reinjects after
    - Preserves tenant_id even if upcaster removes/renames fields
    - Logs warning if tenant_id is missing from event data

    Attributes:
        _tenant_field: The field name for tenant ID (default: "tenant_id")

    Note:
        The mixin uses super() to call the next class in MRO, so it must
        be placed before the base upcaster class.
    """

    # These can be overridden in subclasses
    _tenant_field: str = "tenant_id"

    def _get_tenant_field(self) -> str:
        """Get the tenant field name.

        Override this to customize the tenant field name per upcaster.

        Returns:
            The tenant field name.
        """
        return getattr(self, "_tenant_field", "tenant_id")

    # ── IEventUpcaster Protocol Methods ─────────────────────────────────

    @property
    def event_type(self) -> str:
        """The domain event class name this upcaster handles.

        Delegates to base upcaster.
        """
        return super().event_type  # type: ignore[misc, no-any-return]

    @property
    def source_version(self) -> int:
        """The source schema version this upcaster transforms from.

        Delegates to base upcaster.
        """
        return super().source_version  # type: ignore[misc, no-any-return]

    @property
    def target_version(self) -> int:
        """The target schema version this upcaster transforms to.

        Delegates to base upcaster.
        """
        return super().target_version  # type: ignore[misc, no-any-return]

    def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Transform event data while preserving tenant context.

        Args:
            event_data: Raw event dict with 'aggregate_id' and 'aggregate_type'.

        Returns:
            Updated dictionary in the target schema version with tenant_id preserved.
        """
        tenant_field = self._get_tenant_field()

        # Extract tenant_id before transformation
        tenant_id = event_data.get(tenant_field)

        if tenant_id is None:
            logger.warning(
                f"Tenant ID field '{tenant_field}' not found in event data for "
                f"upcaster {self.__class__.__name__}. Event type: {self.event_type}, "
                f"Source version: {self.source_version}. "
                "This may indicate a missing tenant field in the event schema."
            )

        # Perform the upcasting transformation
        upcasted_data = super().upcast(event_data)  # type: ignore[misc]

        # Reinject tenant_id if it was removed or modified
        if tenant_id is not None:
            if tenant_field not in upcasted_data:
                # Tenant field was removed by upcaster, restore it
                upcasted_data[tenant_field] = tenant_id
                logger.debug(
                    f"Restored tenant_id '{tenant_id}' to upcasted event "
                    f"(event_type={self.event_type}, version={self.target_version})"
                )
            elif upcasted_data.get(tenant_field) != tenant_id:
                # Tenant field was modified, restore original
                original_tenant = upcasted_data.get(tenant_field)
                upcasted_data[tenant_field] = tenant_id
                logger.warning(
                    f"Upcaster {self.__class__.__name__} modified tenant_id from "
                    f"'{tenant_id}' to '{original_tenant}'. Restored original value. "
                    f"Event type: {self.event_type}, Source version: {self.source_version}"
                )

        return upcasted_data  # type: ignore[no-any-return]
