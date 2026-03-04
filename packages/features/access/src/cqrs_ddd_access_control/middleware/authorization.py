"""AuthorizationMiddleware — pre-check resource IDs + post-filter result entities."""

from __future__ import annotations

import logging
import operator
from typing import Any, cast

from cqrs_ddd_identity import get_access_token, get_current_principal_or_none

from ..exceptions import PermissionDeniedError
from ..models import AuthorizationConfig, CheckAccessItem, _resolve_bypass_roles
from ..ports import IAuthorizationPort

logger = logging.getLogger(__name__)


def _getattr_dotted(obj: Any, path: str) -> Any:
    """Resolve a dotted attribute path (e.g. ``"query_options.spec"``)."""
    return operator.attrgetter(path)(obj)


def _setattr_dotted(obj: Any, path: str, value: Any) -> Any:
    """Set a dotted attribute path via ``model_copy`` for frozen models."""
    parts = path.split(".")
    if len(parts) == 1:
        if hasattr(obj, "model_copy"):
            return obj.model_copy(update={parts[0]: value})
        setattr(obj, parts[0], value)
        return obj

    # Nested: rebuild from leaf to root
    current = obj
    parents: list[tuple[Any, str]] = []
    for part in parts[:-1]:
        parents.append((current, part))
        current = getattr(current, part)

    # Set the leaf value
    if hasattr(current, "model_copy"):
        current = current.model_copy(update={parts[-1]: value})
    else:
        setattr(current, parts[-1], value)

    # Propagate up
    for parent, attr_name in reversed(parents):
        if hasattr(parent, "model_copy"):
            parent = parent.model_copy(update={attr_name: current})
        else:
            setattr(parent, attr_name, current)
        current = parent

    return current


class AuthorizationMiddleware:
    """Pre-check resource IDs before handler; post-filter result entities.

    Parameters
    ----------
    authorization_port:
        Runtime authorization port.
    config:
        Middleware configuration.
    bypass_roles:
        Roles that skip authorization. Falls back to ``AUTH_BYPASS_ROLES`` env.
    """

    def __init__(
        self,
        authorization_port: IAuthorizationPort,
        config: AuthorizationConfig,
        bypass_roles: frozenset[str] | None = None,
    ) -> None:
        self._port = authorization_port
        self._config = config
        self._bypass_roles = _resolve_bypass_roles(bypass_roles)

    async def _run_pre_check(
        self,
        _message: Any,
        resource_type: str | None,
        resource_ids: list[str],
        access_token: Any,
        auth_context: dict[str, Any] | None,
        principal: Any,
    ) -> None:
        """Check per resource ID; raise on first denied (unless fail_silently)."""
        if not (resource_ids and self._config.required_actions and resource_type):
            return
        items = [
            CheckAccessItem(
                resource_type=resource_type,
                action=action,
                resource_ids=resource_ids,
            )
            for action in self._config.required_actions
        ]
        batch_result = await self._port.check_access_batch(
            access_token,
            items,
            auth_context=auth_context,
            role_names=list(principal.roles) if principal else None,
        )
        for rid in resource_ids:
            allowed = batch_result.is_allowed(
                resource_type,
                rid,
                set(self._config.required_actions),
                action_quantifier=self._config.action_quantifier,
            )
            if not allowed and not self._config.fail_silently:
                raise PermissionDeniedError(
                    resource_type=resource_type,
                    action=",".join(self._config.required_actions),
                    resource_ids=[rid],
                    reason="Access denied by pre-check",
                )

    async def __call__(self, message: Any, next_handler: Any) -> Any:
        principal = get_current_principal_or_none()
        access_token = get_access_token()

        # Bypass roles check
        if (
            principal
            and self._bypass_roles
            and principal.has_any_role(*self._bypass_roles)
        ):
            return await next_handler(message)

        # Deny anonymous if configured
        if principal is None and self._config.deny_anonymous:
            raise PermissionDeniedError(
                resource_type=self._resolve_resource_type(message),
                action=",".join(self._config.required_actions),
                reason="Anonymous access denied",
            )

        # Pre-check: extract resource IDs → check_access_batch
        resource_type = self._resolve_resource_type(message)
        resource_ids = self._extract_resource_ids(message)
        auth_context = self._resolve_auth_context(message)

        await self._run_pre_check(
            message,
            resource_type,
            resource_ids or [],
            access_token,
            auth_context,
            principal,
        )

        result = await next_handler(message)

        # Post-filter: filter unauthorized entities from result
        if self._config.result_entities_attr and resource_type:
            result = await self._filter_result(
                result,
                resource_type,
                access_token,
                auth_context,
                principal,
            )

        return result

    def _resolve_resource_type(self, message: Any) -> str | None:
        """Resolve resource type from config or message attribute."""
        if self._config.resource_type:
            return self._config.resource_type
        if self._config.resource_type_attr:
            return cast(
                "str | None", _getattr_dotted(message, self._config.resource_type_attr)
            )
        return None

    def _extract_resource_ids(self, message: Any) -> list[str] | None:
        """Extract resource IDs from the command/query message."""
        if not self._config.resource_id_attr:
            return None
        val = _getattr_dotted(message, self._config.resource_id_attr)
        if val is None:
            return None
        if isinstance(val, list):
            return [str(v) for v in val]
        return [str(val)]

    def _resolve_auth_context(self, message: Any) -> dict[str, Any] | None:
        """Build auth context from provider if configured."""
        if self._config.auth_context_provider:
            return self._config.auth_context_provider(message)
        return None

    async def _filter_result(
        self,
        result: Any,
        resource_type: str,
        access_token: str | None,
        auth_context: dict[str, Any] | None,
        principal: Any,
    ) -> Any:
        """Post-filter: remove unauthorized entities from result."""
        if not self._config.result_entities_attr:
            return result
        entities_attr: str = self._config.result_entities_attr
        try:
            entities = _getattr_dotted(result, entities_attr)
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

        items = [
            CheckAccessItem(
                resource_type=resource_type,
                action=action,
                resource_ids=entity_ids,
            )
            for action in self._config.required_actions
        ]
        batch_result = await self._port.check_access_batch(
            access_token,
            items,
            auth_context=auth_context,
            role_names=list(principal.roles) if principal else None,
        )

        filtered = [
            e
            for e in entities
            if batch_result.is_allowed(
                resource_type,
                str(getattr(e, self._config.entity_id_attr)),
                set(self._config.required_actions),
                action_quantifier=self._config.action_quantifier,
            )
        ]
        return _setattr_dotted(result, entities_attr, filtered)
