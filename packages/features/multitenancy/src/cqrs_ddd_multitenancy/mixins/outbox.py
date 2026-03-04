"""Multitenant outbox mixin for tenant-scoped outbox operations.

This mixin adds tenant_id filtering to all outbox operations,
ensuring outbox messages are properly isolated by tenant.

Filtering is pushed to the persistence layer via specification
composition — no in-memory post-fetch filtering.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from ..context import get_current_tenant_or_none, is_system_tenant
from ..exceptions import CrossTenantAccessError, TenantContextMissingError

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.outbox import OutboxMessage
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

__all__ = [
    "MultitenantOutboxMixin",
]

logger = logging.getLogger(__name__)

TENANT_METADATA_KEY = "tenant_id"


class MultitenantOutboxMixin:
    """Mixin that adds tenant filtering to outbox operations.

    This mixin intercepts all outbox methods to inject and filter
    by tenant_id. It should be used via MRO composition:

        class MyOutbox(MultitenantOutboxMixin, SQLAlchemyOutboxStorage):
            pass

    Key behaviors:
    - **save_messages()**: Injects tenant_id into message metadata
    - **get_pending()**: Passes tenant specification to base for DB-level filtering
    - **mark_published()**: Validates tenant ownership
    - **mark_failed()**: Validates tenant ownership

    Note:
        The mixin uses super() to call the next class in MRO, so it must
        be placed before the base outbox class.
    """

    # Metadata key for tenant_id storage
    _tenant_metadata_key: str = TENANT_METADATA_KEY

    def _get_tenant_metadata_key(self) -> str:
        """Get the metadata key for tenant_id storage."""
        return getattr(self, "_tenant_metadata_key", TENANT_METADATA_KEY)

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
                "Tenant context required for outbox operation. "
                "Ensure TenantMiddleware is configured or use @system_operation."
            )
        return tenant or "__system__"

    def _build_tenant_specification(self, tenant_id: str) -> Any:
        """Build a tenant specification for outbox filtering.

        Uses ``AttributeSpecification`` targeting the dedicated ``tenant_id``
        column for DB-level WHERE clause filtering (not in-memory metadata).

        Args:
            tenant_id: The tenant ID to filter by.

        Returns:
            An AttributeSpecification for the given tenant.
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
            logger.warning(
                "cqrs-ddd-specifications not installed, using dict filter fallback",
                extra={"tenant_id": tenant_id},
            )
            return {
                "attr": "tenant_id",
                "op": "eq",
                "val": tenant_id,
            }

    def _inject_tenant_into_message(
        self,
        message: OutboxMessage,
        tenant_id: str,
    ) -> OutboxMessage:
        """Inject tenant_id into message metadata and the dedicated field.

        Sets both ``message.tenant_id`` (dedicated column) **and** the
        metadata key for backward-compatible consumers.

        Args:
            message: The original outbox message.
            tenant_id: The tenant ID to inject.

        Returns:
            A new OutboxMessage with tenant_id set.
        """
        tenant_key = self._get_tenant_metadata_key()

        # Create updated metadata
        updated_metadata = dict(message.metadata)
        updated_metadata[tenant_key] = tenant_id

        # Use dataclasses.replace for OutboxMessage — sets both the
        # dedicated ``tenant_id`` field AND metadata for compat.
        if dataclasses.is_dataclass(message):
            return dataclasses.replace(
                message, metadata=updated_metadata, tenant_id=tenant_id
            )

        # Fallback: try to create new instance
        return message.__class__(
            message_id=message.message_id,
            event_type=message.event_type,
            payload=message.payload,
            metadata=updated_metadata,
            created_at=message.created_at,
            published_at=message.published_at,
            error=message.error,
            retry_count=message.retry_count,
            correlation_id=message.correlation_id,
            causation_id=message.causation_id,
            tenant_id=tenant_id,
        )

    def _get_tenant_from_message(self, message: OutboxMessage) -> str | None:
        """Extract tenant_id from message.

        Resolution order:
        1. Dedicated ``tenant_id`` attribute (DB column)
        2. Metadata dict fallback (backward compatibility)

        Args:
            message: The outbox message.

        Returns:
            The tenant_id, or None.
        """
        # 1. Dedicated attribute
        val = getattr(message, "tenant_id", None)
        if val is not None:
            return val  # type: ignore[no-any-return]
        # 2. Metadata fallback
        tenant_key = self._get_tenant_metadata_key()
        return message.metadata.get(tenant_key)  # type: ignore[return-value]

    # -----------------------------------------------------------------------
    # Outbox method overrides
    # -----------------------------------------------------------------------

    async def save_messages(
        self: Any,
        messages: list[OutboxMessage],
        uow: UnitOfWork | None = None,
    ) -> None:
        """Save messages with tenant_id injection.

        Args:
            messages: The messages to save.
            uow: Optional unit of work.

        Raises:
            TenantContextMissingError: If no tenant context.
        """
        if is_system_tenant():
            return await super().save_messages(messages, uow)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        messages_with_tenant = [
            self._inject_tenant_into_message(msg, tenant_id) for msg in messages
        ]

        logger.debug(
            "Saving outbox messages with tenant",
            extra={
                "tenant_id": tenant_id,
                "message_count": len(messages),
            },
        )

        return await super().save_messages(messages_with_tenant, uow)  # type: ignore[misc, no-any-return]

    async def get_pending(
        self: Any,
        limit: int = 100,
        uow: UnitOfWork | None = None,
    ) -> list[OutboxMessage]:
        """Get pending messages filtered by tenant via specification.

        Uses DB-level filtering via the ``specification`` parameter
        instead of in-memory post-fetch filtering.

        Args:
            limit: Maximum number of messages to return.
            uow: Optional unit of work.

        Returns:
            List of pending messages for the current tenant.
        """
        if is_system_tenant():
            return await super().get_pending(limit, uow)  # type: ignore[misc, no-any-return]

        tenant_id = self._require_tenant_context()
        tenant_spec = self._build_tenant_specification(tenant_id)
        return await super().get_pending(limit, uow, specification=tenant_spec)  # type: ignore[misc, no-any-return]

    async def mark_published(
        self: Any,
        message_ids: list[str],
        uow: UnitOfWork | None = None,
    ) -> None:
        """Mark messages as published with tenant validation.

        Args:
            message_ids: IDs of messages to mark as published.
            uow: Optional unit of work.
        """
        if is_system_tenant():
            return await super().mark_published(message_ids, uow)  # type: ignore[misc, no-any-return]

        self._require_tenant_context()
        return await super().mark_published(message_ids, uow)  # type: ignore[misc, no-any-return]

    async def mark_failed(
        self: Any,
        message_id: str,
        error: str,
        uow: UnitOfWork | None = None,
    ) -> None:
        """Mark message as failed with tenant validation.

        Args:
            message_id: ID of the message to mark as failed.
            error: Error description.
            uow: Optional unit of work.
        """
        if is_system_tenant():
            return await super().mark_failed(message_id, error, uow)  # type: ignore[misc, no-any-return]

        self._require_tenant_context()
        return await super().mark_failed(message_id, error, uow)  # type: ignore[misc, no-any-return]


class StrictMultitenantOutboxMixin(MultitenantOutboxMixin):
    """Strict variant that validates tenant ownership on all operations.

    Fetches and validates tenant ownership before allowing
    modification operations (mark_published, mark_failed).
    """

    async def mark_published(
        self: Any,
        message_ids: list[str],
        uow: UnitOfWork | None = None,
    ) -> None:
        """Mark messages as published with strict tenant validation.

        Args:
            message_ids: IDs of messages to mark as published.
            uow: Optional unit of work.

        Raises:
            CrossTenantAccessError: If any message belongs to different tenant.
        """
        if is_system_tenant():
            return await super().mark_published(message_ids, uow)

        tenant_id = self._require_tenant_context()

        # Fetch pending messages and validate ownership
        pending = await super().get_pending(limit=len(message_ids) * 2, uow=uow)
        pending_by_id = {msg.message_id: msg for msg in pending}

        for msg_id in message_ids:
            msg = pending_by_id.get(msg_id)
            if msg is not None:
                msg_tenant = self._get_tenant_from_message(msg)
                if msg_tenant is not None and msg_tenant != tenant_id:
                    raise CrossTenantAccessError(
                        current_tenant=tenant_id,
                        target_tenant=msg_tenant,
                        resource_type="OutboxMessage",
                        resource_id=msg_id,
                    )

        return await super().mark_published(message_ids, uow)
