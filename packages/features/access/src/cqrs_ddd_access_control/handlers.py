"""Command handlers for ACL operations.

Handlers emit request events — they do **not** call the admin port directly.
The priority event handlers (``acl_handlers``) process those events within
the same UoW transaction.
"""

from __future__ import annotations

from typing import Any

from cqrs_ddd_core.cqrs.handler import CommandHandler
from cqrs_ddd_core.cqrs.response import CommandResponse
from cqrs_ddd_identity import get_current_principal

from .commands import GrantACL, GrantOwnershipACL, RevokeACL, SetResourcePublic
from .events import (
    ACLGrantRequested,
    ACLRevokeRequested,
    ResourceTypePublicSetRequested,
)
from .models import AccessRule


class GrantACLHandler(CommandHandler[dict[str, Any]]):
    """Build ``AccessRule``(s) from command fields, emit ``ACLGrantRequested``."""

    async def handle(self, command: GrantACL) -> CommandResponse[dict[str, Any]]:  # type: ignore[override]
        rule = AccessRule(
            principal_name=command.principal_name,
            role_name=command.role_name,
            action=command.action,
            resource_id=command.resource_id,
            conditions=command.conditions,
            specification_dsl=command.specification_dsl,
        )
        event = ACLGrantRequested(
            resource_type=command.resource_type,
            resource_id=command.resource_id,
            access_rules=[rule],
            aggregate_id=command.resource_id,
            aggregate_type=command.resource_type,
            correlation_id=command.correlation_id,
            causation_id=command.command_id,
        )
        return CommandResponse(
            result={"status": "requested"},
            events=[event],
            correlation_id=command.correlation_id,
            causation_id=command.command_id,
        )


class RevokeACLHandler(CommandHandler[dict[str, Any]]):
    """Emit ``ACLRevokeRequested``."""

    async def handle(self, command: RevokeACL) -> CommandResponse[dict[str, Any]]:  # type: ignore[override]
        event = ACLRevokeRequested(
            resource_type=command.resource_type,
            action=command.action,
            principal_name=command.principal_name,
            role_name=command.role_name,
            resource_id=command.resource_id,
            aggregate_id=command.resource_id,
            aggregate_type=command.resource_type,
            correlation_id=command.correlation_id,
            causation_id=command.command_id,
        )
        return CommandResponse(
            result={"status": "requested"},
            events=[event],
            correlation_id=command.correlation_id,
            causation_id=command.command_id,
        )


class SetResourcePublicHandler(CommandHandler[dict[str, Any]]):
    """Emit ``ResourceTypePublicSetRequested``."""

    async def handle(  # type: ignore[override]
        self, command: SetResourcePublic
    ) -> CommandResponse[dict[str, Any]]:
        event = ResourceTypePublicSetRequested(
            resource_type=command.resource_type,
            is_public=command.is_public,
            aggregate_type=command.resource_type,
            correlation_id=command.correlation_id,
            causation_id=command.command_id,
        )
        return CommandResponse(
            result={"status": "requested"},
            events=[event],
            correlation_id=command.correlation_id,
            causation_id=command.command_id,
        )


class GrantOwnershipACLHandler(CommandHandler[dict[str, Any]]):
    """Grant the current principal full access to a resource they just created."""

    async def handle(  # type: ignore[override]
        self, command: GrantOwnershipACL
    ) -> CommandResponse[dict[str, Any]]:
        principal = get_current_principal()
        rules = [
            AccessRule(
                principal_name=principal.username,
                action=action,
                resource_id=command.resource_id,
            )
            for action in command.actions
        ]
        event = ACLGrantRequested(
            resource_type=command.resource_type,
            resource_id=command.resource_id,
            access_rules=rules,
            aggregate_id=command.resource_id,
            aggregate_type=command.resource_type,
            correlation_id=command.correlation_id,
            causation_id=command.command_id,
        )
        return CommandResponse(
            result={"status": "requested", "principal": principal.username},
            events=[event],
            correlation_id=command.correlation_id,
            causation_id=command.command_id,
        )
