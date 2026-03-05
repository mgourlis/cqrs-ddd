"""Priority (synchronous) event handlers for ACL operations.

These execute within the **same UoW transaction** as the domain command.
Completion events are persisted to the event store, not emitted via the
event dispatcher.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .events import (
    ACLGranted,
    ACLGrantRequested,
    ACLRevoked,
    ACLRevokeRequested,
    ResourceTypePublicSet,
    ResourceTypePublicSetRequested,
)
from .exceptions import ACLError

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.ports.event_dispatcher import IEventDispatcher
    from cqrs_ddd_core.ports.event_store import IEventStore

    from .ports import IAuthorizationAdminPort

logger = logging.getLogger(__name__)


class ACLGrantRequestedHandler:
    """Process ACL grant requests via the admin port.

    When ``enforce_tenant_isolation`` is True, a tenant-scoping condition is
    injected into every ACL grant.
    """

    def __init__(
        self,
        admin_port: IAuthorizationAdminPort,
        event_store: IEventStore | None = None,
        enforce_tenant_isolation: bool = False,
    ) -> None:
        self._admin_port = admin_port
        self._event_store = event_store
        self._enforce_tenant_isolation = enforce_tenant_isolation

    _TENANT_ISOLATION_CONDITION: dict[str, Any] = {
        "op": "=",
        "source": "resource",
        "attr": "tenant_id",
        "val": "$context.tenant_id",
    }

    def _merge_tenant_condition(self, raw_conditions: Any) -> dict[str, Any] | None:
        """Return conditions with tenant isolation injected when required."""
        conditions = dict(raw_conditions) if raw_conditions else None
        if not self._enforce_tenant_isolation:
            return conditions
        tenant_cond = self._TENANT_ISOLATION_CONDITION
        if conditions is None:
            return tenant_cond
        return {"op": "and", "conditions": [conditions, tenant_cond]}

    async def _call_admin_port(
        self, event: ACLGrantRequested, rule: Any, conditions: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Dispatch to the appropriate admin-port method based on the rule."""
        resource_external_id = rule.resource_id or event.resource_id
        if rule.specification_dsl:
            return await self._admin_port.create_acl_from_specification(
                resource_type=event.resource_type,
                action=rule.action,
                principal_name=rule.principal_name,
                role_name=rule.role_name,
                resource_external_id=resource_external_id,
                specification_dsl=rule.specification_dsl,
            )
        return await self._admin_port.create_acl(
            resource_type=event.resource_type,
            action=rule.action,
            principal_name=rule.principal_name,
            role_name=rule.role_name,
            resource_external_id=resource_external_id,
            conditions=conditions,
        )

    def _build_granted_event(
        self,
        event: ACLGrantRequested,
        rule: Any,
        result: dict[str, Any],
        conditions: dict[str, Any] | None,
    ) -> ACLGranted:
        """Construct the ACLGranted completion event."""
        return ACLGranted(
            resource_type=event.resource_type,
            action=rule.action,
            principal_name=rule.principal_name,
            role_name=rule.role_name,
            resource_id=rule.resource_id or event.resource_id,
            acl_id=result.get("id"),
            conditions=conditions,
            specification_dsl=rule.specification_dsl,
            previous_state=result.get("previous_state"),
            aggregate_id=event.aggregate_id,
            aggregate_type=event.aggregate_type,
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
        )

    async def __call__(self, event: ACLGrantRequested) -> None:
        for rule in event.access_rules:
            try:
                conditions = self._merge_tenant_condition(rule.conditions)
                result = await self._call_admin_port(event, rule, conditions)
                completion = self._build_granted_event(event, rule, result, conditions)
                if self._event_store is not None:
                    await self._event_store.append(completion)  # type: ignore[arg-type]
            except ACLError:
                raise
            except Exception as exc:
                logger.exception(
                    "Failed to grant ACL for %s:%s", event.resource_type, rule.action
                )
                raise ACLError(
                    f"ACL grant failed for {event.resource_type}:{rule.action}: {exc}",
                    details={
                        "resource_type": event.resource_type,
                        "action": rule.action,
                        "error": str(exc),
                    },
                ) from exc


class ACLRevokeRequestedHandler:
    """Process ACL revoke requests via the admin port."""

    def __init__(
        self,
        admin_port: IAuthorizationAdminPort,
        event_store: IEventStore | None = None,
    ) -> None:
        self._admin_port = admin_port
        self._event_store = event_store

    async def __call__(self, event: ACLRevokeRequested) -> None:
        try:
            result = await self._admin_port.delete_acl_by_key(
                resource_type=event.resource_type,
                action=event.action,
                principal_name=event.principal_name,
                role_name=event.role_name,
                resource_external_id=event.resource_id,
            )
            prev = result.get("previous_state") if isinstance(result, dict) else None
            completion = ACLRevoked(
                resource_type=event.resource_type,
                action=event.action,
                principal_name=event.principal_name,
                role_name=event.role_name,
                resource_id=event.resource_id,
                previous_state=prev,
                aggregate_id=event.aggregate_id,
                aggregate_type=event.aggregate_type,
                correlation_id=event.correlation_id,
                causation_id=event.event_id,
            )
            if self._event_store is not None:
                await self._event_store.append(completion)  # type: ignore[arg-type]

        except Exception as exc:
            logger.exception(
                "Failed to revoke ACL for %s:%s", event.resource_type, event.action
            )
            raise ACLError(
                f"ACL revoke failed for {event.resource_type}:{event.action}: {exc}",
                details={
                    "resource_type": event.resource_type,
                    "action": event.action,
                    "error": str(exc),
                },
            ) from exc


class ResourceTypePublicSetHandler:
    """Process resource type public flag changes via the admin port."""

    def __init__(
        self,
        admin_port: IAuthorizationAdminPort,
        event_store: IEventStore | None = None,
    ) -> None:
        self._admin_port = admin_port
        self._event_store = event_store

    async def __call__(self, event: ResourceTypePublicSetRequested) -> None:
        try:
            result = await self._admin_port.set_resource_type_public(
                event.resource_type, event.is_public
            )
            prev_pub = (
                result.get("previous_public") if isinstance(result, dict) else None
            )
            completion = ResourceTypePublicSet(
                resource_type=event.resource_type,
                is_public=event.is_public,
                previous_public=prev_pub,
                aggregate_type=event.resource_type,
                correlation_id=event.correlation_id,
                causation_id=event.event_id,
            )
            if self._event_store is not None:
                await self._event_store.append(completion)  # type: ignore[arg-type]

        except Exception as exc:
            logger.exception("Failed to set public for %s", event.resource_type)
            raise ACLError(
                f"Set public failed for {event.resource_type}: {exc}",
                details={
                    "resource_type": event.resource_type,
                    "error": str(exc),
                },
            ) from exc


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def register_priority_acl_handlers(
    event_dispatcher: IEventDispatcher[DomainEvent],
    admin_port: IAuthorizationAdminPort,
    event_store: IEventStore | None = None,
    enforce_tenant_isolation: bool = False,
) -> None:
    """Wire all three priority event handlers into the event dispatcher.

    Parameters
    ----------
    event_dispatcher:
        The event dispatcher to register handlers with.
    admin_port:
        Authorization admin port for ACL CRUD operations.
    event_store:
        Optional event store for persisting completion events.
    enforce_tenant_isolation:
        When True, ``ACLGrantRequestedHandler`` auto-injects a
        ``tenant_id`` condition into ACL conditions.
    """
    grant_handler = ACLGrantRequestedHandler(
        admin_port,
        event_store,
        enforce_tenant_isolation,
    )
    revoke_handler = ACLRevokeRequestedHandler(
        admin_port,
        event_store,
    )
    public_handler = ResourceTypePublicSetHandler(
        admin_port,
        event_store,
    )

    event_dispatcher.register(
        ACLGrantRequested,
        lambda event: grant_handler(event),
    )
    event_dispatcher.register(
        ACLRevokeRequested,
        lambda event: revoke_handler(event),
    )
    event_dispatcher.register(
        ResourceTypePublicSetRequested,
        lambda event: public_handler(event),
    )
