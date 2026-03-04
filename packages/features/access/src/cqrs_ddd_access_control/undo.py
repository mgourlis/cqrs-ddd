"""Undo executors for ACL operations.

Requires ``cqrs-ddd-advanced``. Undo executors reverse ACL operations by
sending commands through the mediator, ensuring the undo goes through the
same command → event → priority handler pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cqrs_ddd_core import DomainEvent

from .commands import GrantACL, RevokeACL, SetResourcePublic
from .events import ACLGranted, ACLRevoked, ResourceTypePublicSet

if TYPE_CHECKING:
    from cqrs_ddd_core.cqrs.mediator import Mediator


class ACLGrantedUndoExecutor:
    """Undo: send ``RevokeACL`` command. Redo: send ``GrantACL`` command."""

    event_type = "ACLGranted"

    def __init__(self, mediator: Mediator) -> None:
        self._mediator = mediator

    async def can_undo(self, event: ACLGranted) -> bool:
        return event.resource_type is not None and event.action is not None

    async def undo(self, event: ACLGranted) -> list[DomainEvent]:
        command = RevokeACL(
            resource_type=event.resource_type,
            action=event.action,
            principal_name=event.principal_name,
            role_name=event.role_name,
            resource_id=event.resource_id,
        )
        response = await self._mediator.send(command)
        return response.events

    async def redo(
        self, event: ACLGranted, _undo_event: DomainEvent
    ) -> list[DomainEvent]:
        command = GrantACL(
            resource_type=event.resource_type,
            action=event.action,
            principal_name=event.principal_name,
            role_name=event.role_name,
            resource_id=event.resource_id,
            conditions=event.conditions,
            specification_dsl=event.specification_dsl,
        )
        response = await self._mediator.send(command)
        return response.events


class ACLRevokedUndoExecutor:
    """Undo: send ``GrantACL`` with previous conditions. Redo: send ``RevokeACL``."""

    event_type = "ACLRevoked"

    def __init__(self, mediator: Mediator) -> None:
        self._mediator = mediator

    async def can_undo(self, event: ACLRevoked) -> bool:
        return event.previous_state is not None

    async def undo(self, event: ACLRevoked) -> list[DomainEvent]:
        prev: dict[str, Any] = event.previous_state or {}
        command = GrantACL(
            resource_type=event.resource_type,
            action=event.action,
            principal_name=event.principal_name,
            role_name=event.role_name,
            resource_id=event.resource_id,
            conditions=prev.get("conditions"),
            specification_dsl=prev.get("specification_dsl"),
        )
        response = await self._mediator.send(command)
        return response.events

    async def redo(
        self, event: ACLRevoked, _undo_event: DomainEvent
    ) -> list[DomainEvent]:
        command = RevokeACL(
            resource_type=event.resource_type,
            action=event.action,
            principal_name=event.principal_name,
            role_name=event.role_name,
            resource_id=event.resource_id,
        )
        response = await self._mediator.send(command)
        return response.events


class ResourceTypePublicSetUndoExecutor:
    """Undo: send SetResourcePublic with previous value. Redo: send original."""

    event_type = "ResourceTypePublicSet"

    def __init__(self, mediator: Mediator) -> None:
        self._mediator = mediator

    async def can_undo(self, event: ResourceTypePublicSet) -> bool:
        return event.previous_public is not None

    async def undo(self, event: ResourceTypePublicSet) -> list[DomainEvent]:
        command = SetResourcePublic(
            resource_type=event.resource_type,
            is_public=(
                event.previous_public
                if event.previous_public is not None
                else not event.is_public
            ),
        )
        response = await self._mediator.send(command)
        return response.events

    async def redo(
        self, event: ResourceTypePublicSet, _undo_event: DomainEvent
    ) -> list[DomainEvent]:
        command = SetResourcePublic(
            resource_type=event.resource_type,
            is_public=event.is_public,
        )
        response = await self._mediator.send(command)
        return response.events


def register_acl_undo_executors(
    undo_registry: Any,
    mediator: Mediator,
) -> None:
    """Register all ACL undo executors into an ``IUndoExecutorRegistry``."""
    undo_registry.register(ACLGrantedUndoExecutor(mediator))
    undo_registry.register(ACLRevokedUndoExecutor(mediator))
    undo_registry.register(ResourceTypePublicSetUndoExecutor(mediator))
