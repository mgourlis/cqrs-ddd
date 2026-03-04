"""StatefulABACAdapter — implements IAuthorizationPort via stateful-abac-sdk."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...models import (
    AuthorizationConditionsResult,
    AuthorizationFilter,
    CheckAccessBatchResult,
    CheckAccessItem,
    FieldMapping,
    GetPermittedActionsItem,
)
from ...ports import IAuthorizationPort
from .condition_converter import ConditionConverter

if TYPE_CHECKING:
    from .config import ABACClientConfig

logger = logging.getLogger(__name__)


class StatefulABACAdapter(IAuthorizationPort):
    """Runtime authorization via stateful-abac-policy-engine.

    Delegates to the stateful-abac-sdk client. Supports dynamic realm
    resolution for realm-per-tenant isolation.

    Parameters
    ----------
    config:
        ABAC client configuration.
    """

    def __init__(self, config: ABACClientConfig) -> None:
        self._config = config
        self._clients: dict[str, Any] = {}

    def _get_client(self) -> Any:
        """Get or create an SDK client for the current realm."""
        from stateful_abac_sdk import StatefulABACClientFactory

        realm = self._config.resolve_realm()
        if realm not in self._clients:
            self._clients[realm] = StatefulABACClientFactory.create(
                mode=self._config.mode,
                realm=realm,
                base_url=self._config.base_url or None,
                timeout=self._config.timeout,
            )
        return self._clients[realm]

    async def check_access(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        resource_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> list[str]:
        from stateful_abac_sdk.models import CheckAccessItem as SDKCheckAccessItem

        client = self._get_client()
        if access_token:
            client.set_token(access_token)

        items = [
            SDKCheckAccessItem(
                resource_type_name=resource_type,
                action_name=action,
                external_resource_ids=resource_ids,
            )
        ]
        response = await client.auth.check_access(
            items,
            auth_context=auth_context,
            role_names=role_names,
            chunk_size=self._config.chunk_size,
            max_concurrent=self._config.max_concurrent,
        )

        for result in response.results:
            if (
                result.resource_type_name == resource_type
                and result.action_name == action
            ):
                if isinstance(result.answer, bool):
                    return resource_ids or [] if result.answer else []
                return [str(rid) for rid in result.answer]
        return []

    async def check_access_batch(
        self,
        access_token: str | None,
        items: list[CheckAccessItem],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> CheckAccessBatchResult:
        from stateful_abac_sdk.models import CheckAccessItem as SDKCheckAccessItem

        client = self._get_client()
        if access_token:
            client.set_token(access_token)

        sdk_items = [
            SDKCheckAccessItem(
                resource_type_name=item.resource_type,
                action_name=item.action,
                external_resource_ids=item.resource_ids,
            )
            for item in items
        ]
        response = await client.auth.check_access(
            sdk_items,
            auth_context=auth_context,
            role_names=role_names,
            chunk_size=self._config.chunk_size,
            max_concurrent=self._config.max_concurrent,
        )

        result = CheckAccessBatchResult()
        for resp_item in response.results:
            if isinstance(resp_item.answer, bool):
                if resp_item.answer:
                    result.global_permissions.add(resp_item.action_name)
            elif isinstance(resp_item.answer, list):
                for rid in resp_item.answer:
                    key = (resp_item.resource_type_name, str(rid))
                    actions = result.access_map.setdefault(key, set())
                    actions.add(resp_item.action_name)
        return result

    async def get_permitted_actions(
        self,
        access_token: str | None,
        resource_type: str,
        resource_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, list[str]]:
        from stateful_abac_sdk.models import (
            GetPermittedActionsItem as SDKGetPermittedActionsItem,
        )

        client = self._get_client()
        if access_token:
            client.set_token(access_token)

        sdk_items = [
            SDKGetPermittedActionsItem(
                resource_type_name=resource_type,
                external_resource_ids=resource_ids,
            )
        ]
        response = await client.auth.get_permitted_actions(
            sdk_items,
            auth_context=auth_context,
            role_names=role_names,
        )

        result: dict[str, list[str]] = {}
        for item in response.results:
            if item.resource_type_name == resource_type:
                key = item.external_resource_id or "__type__"
                result[key] = item.actions
        return result

    async def get_permitted_actions_batch(
        self,
        access_token: str | None,
        items: list[GetPermittedActionsItem],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, dict[str, list[str]]]:
        from stateful_abac_sdk.models import (
            GetPermittedActionsItem as SDKGetPermittedActionsItem,
        )

        client = self._get_client()
        if access_token:
            client.set_token(access_token)

        sdk_items = [
            SDKGetPermittedActionsItem(
                resource_type_name=item.resource_type,
                external_resource_ids=item.resource_ids,
            )
            for item in items
        ]
        response = await client.auth.get_permitted_actions(
            sdk_items,
            auth_context=auth_context,
            role_names=role_names,
        )

        result: dict[str, dict[str, list[str]]] = {}
        for resp_item in response.results:
            rt = resp_item.resource_type_name
            key = resp_item.external_resource_id or "__type__"
            result.setdefault(rt, {})[key] = resp_item.actions
        return result

    async def get_type_level_permissions(
        self,
        access_token: str | None,
        resource_types: list[str],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, list[str]]:
        from stateful_abac_sdk.models import (
            GetPermittedActionsItem as SDKGetPermittedActionsItem,
        )

        client = self._get_client()
        if access_token:
            client.set_token(access_token)

        sdk_items = [
            SDKGetPermittedActionsItem(
                resource_type_name=rt,
                external_resource_ids=None,
            )
            for rt in resource_types
        ]
        response = await client.auth.get_permitted_actions(
            sdk_items,
            auth_context=auth_context,
            role_names=role_names,
        )

        result: dict[str, list[str]] = {}
        for resp_item in response.results:
            if resp_item.external_resource_id is None:
                result[resp_item.resource_type_name] = resp_item.actions
        return result

    async def get_authorization_conditions(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> AuthorizationConditionsResult:
        client = self._get_client()
        if access_token:
            client.set_token(access_token)

        response = await client.auth.get_authorization_conditions(
            resource_type_name=resource_type,
            action_name=action,
            auth_context=auth_context,
            role_names=role_names,
        )

        cond_dsl = (
            response.conditions_dsl if hasattr(response, "conditions_dsl") else None
        )
        return AuthorizationConditionsResult(
            filter_type=response.filter_type,
            conditions_dsl=cond_dsl,
            has_context_refs=getattr(response, "has_context_refs", False),
        )

    async def get_authorization_filter(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
        field_mapping: FieldMapping | None = None,
    ) -> AuthorizationFilter:
        conditions = await self.get_authorization_conditions(
            access_token,
            resource_type,
            action,
            auth_context=auth_context,
            role_names=role_names,
        )

        if field_mapping is None:
            # No mapping → return raw result
            if conditions.granted_all:
                return AuthorizationFilter.grant_all()
            if conditions.denied_all:
                return AuthorizationFilter.deny_all()
            return AuthorizationFilter.deny_all()

        converter = ConditionConverter(field_mapping)
        return converter.dsl_to_specification(conditions)

    async def list_resource_types(self) -> list[str]:
        client = self._get_client()
        types = await client.resource_types.list()
        return [t.name for t in types]

    async def list_actions(self, _resource_type: str) -> list[str]:
        client = self._get_client()
        actions = await client.actions.list()
        return [a.name for a in actions]
