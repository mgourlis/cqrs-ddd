"""SpecificationAuthMiddleware — single-query authorization.

Merges authorization conditions into ``QueryOptions.specification`` so the
database enforces authorization in a single SQL statement.
"""

from __future__ import annotations

import logging
from typing import Any

from cqrs_ddd_identity import get_access_token, get_current_principal_or_none

from ..exceptions import PermissionDeniedError
from ..models import SpecificationAuthConfig, _resolve_bypass_roles
from ..ports import IAuthorizationPort, IResourceTypeRegistry

logger = logging.getLogger(__name__)


class SpecificationAuthMiddleware:
    """Merge authorization conditions into the query specification.

    Parameters
    ----------
    authorization_port:
        Runtime authorization port.
    config:
        Specification auth configuration.
    resource_type_registry:
        Registry for resolving field mappings.
    bypass_roles:
        Roles that skip authorization.
    """

    def __init__(
        self,
        authorization_port: IAuthorizationPort,
        config: SpecificationAuthConfig,
        resource_type_registry: IResourceTypeRegistry,
        bypass_roles: frozenset[str] | None = None,
    ) -> None:
        self._port = authorization_port
        self._config = config
        self._registry = resource_type_registry
        self._bypass_roles = _resolve_bypass_roles(bypass_roles)

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

        # Resolve field mapping from registry
        rt_config = self._registry.get_config(self._config.resource_type)
        field_mapping = rt_config.field_mapping if rt_config else None

        # Resolve auth context
        auth_context: dict[str, Any] | None = None
        if self._config.auth_context_provider:
            auth_context = self._config.auth_context_provider(message)

        auth_filter = await self._port.get_authorization_filter(
            access_token,
            self._config.resource_type,
            self._config.action,
            auth_context=auth_context,
            role_names=list(principal.roles) if principal else None,
            field_mapping=field_mapping,
        )

        if auth_filter.denied_all:
            raise PermissionDeniedError(
                resource_type=self._config.resource_type,
                action=self._config.action,
                reason="Access denied — all conditions denied",
            )

        if auth_filter.has_filter:
            # Merge auth specification into QueryOptions.specification
            query_options = getattr(message, self._config.query_options_attr, None)
            if query_options is not None:
                if query_options.specification is not None:
                    merged = query_options.specification.merge(
                        auth_filter.filter_specification
                    )
                else:
                    merged = auth_filter.filter_specification

                updated_options = query_options.with_specification(merged)
                message = message.model_copy(
                    update={self._config.query_options_attr: updated_options}
                )

        return await next_handler(message)
