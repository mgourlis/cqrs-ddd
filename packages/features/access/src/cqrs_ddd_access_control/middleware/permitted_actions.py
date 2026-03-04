"""PermittedActionsMiddleware — enrich result entities with permitted actions."""

from __future__ import annotations

import logging
from typing import Any

from cqrs_ddd_identity import get_access_token, get_current_principal_or_none

from ..models import (
    GetPermittedActionsItem,
    PermittedActionsConfig,
    _resolve_bypass_roles,
)
from ..ports import IAuthorizationPort

logger = logging.getLogger(__name__)


class PermittedActionsMiddleware:
    """Post-execution: enrich each result entity with its permitted actions.

    Parameters
    ----------
    authorization_port:
        Runtime authorization port.
    config:
        Permitted actions configuration.
    bypass_roles:
        Roles that skip authorization.
    """

    def __init__(
        self,
        authorization_port: IAuthorizationPort,
        config: PermittedActionsConfig,
        bypass_roles: frozenset[str] | None = None,
    ) -> None:
        self._port = authorization_port
        self._config = config
        self._bypass_roles = _resolve_bypass_roles(bypass_roles)

    async def __call__(self, message: Any, next_handler: Any) -> Any:
        result = await next_handler(message)

        principal = get_current_principal_or_none()
        access_token = get_access_token()

        # Bypass roles — set all actions as permitted (skip lookup)
        if (
            principal
            and self._bypass_roles
            and principal.has_any_role(*self._bypass_roles)
        ):
            return result

        return await self._enrich_result(result, access_token, principal, message)

    async def _enrich_result(
        self,
        result: Any,
        access_token: str | None,
        principal: Any,
        message: Any,
    ) -> Any:
        """Attach permitted_actions to each entity in the result."""
        try:
            entities = getattr(result, self._config.result_entities_attr, None)
        except AttributeError:
            return result

        if not entities or not isinstance(entities, list):
            return result

        entity_ids = [
            str(getattr(e, self._config.entity_id_attr, None))
            for e in entities
            if getattr(e, self._config.entity_id_attr, None) is not None
        ]
        if not entity_ids:
            return result

        # Resolve auth context
        auth_context: dict[str, Any] | None = None
        if self._config.auth_context_provider:
            auth_context = self._config.auth_context_provider(message)

        items = [
            GetPermittedActionsItem(
                resource_type=self._config.resource_type,
                resource_ids=entity_ids,
            ),
        ]
        batch_result = await self._port.get_permitted_actions_batch(
            access_token,
            items,
            auth_context=auth_context,
            role_names=list(principal.roles) if principal else None,
        )

        resource_permissions = batch_result.get(self._config.resource_type, {})

        # Type-level permissions
        type_level: list[str] = []
        if self._config.include_type_level:
            type_perms = await self._port.get_type_level_permissions(
                access_token,
                [self._config.resource_type],
                auth_context=auth_context,
                role_names=list(principal.roles) if principal else None,
            )
            type_level = type_perms.get(self._config.resource_type, [])

        # Enrich entities
        for entity in entities:
            eid = str(getattr(entity, self._config.entity_id_attr, None))
            entity_actions = resource_permissions.get(eid, [])
            merged_actions = list(set(entity_actions) | set(type_level))
            try:
                setattr(entity, self._config.permitted_actions_attr, merged_actions)
            except (AttributeError, TypeError, ValueError):
                # Frozen model — try model_copy
                if hasattr(entity, "model_copy"):
                    idx = entities.index(entity)
                    entities[idx] = entity.model_copy(
                        update={self._config.permitted_actions_attr: merged_actions}
                    )

        return result
