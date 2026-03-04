"""Shared test fixtures for cqrs_ddd_access_control tests."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_access_control.models import (
    AuthorizationConditionsResult,
    AuthorizationDecision,
    AuthorizationFilter,
    CheckAccessBatchResult,
    CheckAccessItem,
    FieldMapping,
    GetPermittedActionsItem,
)
from cqrs_ddd_identity import Principal

# ---------------------------------------------------------------------------
# Stub: IAuthorizationPort
# ---------------------------------------------------------------------------


class StubAuthorizationPort:
    """In-memory stub for IAuthorizationPort."""

    def __init__(self) -> None:
        self.allowed_ids: dict[tuple[str, str], list[str]] = {}
        self.conditions: dict[tuple[str, str], AuthorizationConditionsResult] = {}
        self.permitted_actions: dict[str, dict[str, list[str]]] = {}
        self.type_level_perms: dict[str, list[str]] = {}

    async def check_access(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        resource_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> list[str]:
        key = (resource_type, action)
        return self.allowed_ids.get(key, [])

    async def check_access_batch(
        self,
        access_token: str | None,
        items: list[CheckAccessItem],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> CheckAccessBatchResult:
        result = CheckAccessBatchResult()
        for item in items:
            allowed = self.allowed_ids.get((item.resource_type, item.action), [])
            for rid in allowed:
                key = (item.resource_type, rid)
                actions = result.access_map.setdefault(key, set())
                actions.add(item.action)
        return result

    async def get_permitted_actions(
        self,
        access_token: str | None,
        resource_type: str,
        resource_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, list[str]]:
        return self.permitted_actions.get(resource_type, {})

    async def get_permitted_actions_batch(
        self,
        access_token: str | None,
        items: list[GetPermittedActionsItem],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, dict[str, list[str]]]:
        result: dict[str, dict[str, list[str]]] = {}
        for item in items:
            result[item.resource_type] = self.permitted_actions.get(
                item.resource_type, {}
            )
        return result

    async def get_type_level_permissions(
        self,
        access_token: str | None,
        resource_types: list[str],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, list[str]]:
        return {rt: self.type_level_perms.get(rt, []) for rt in resource_types}

    async def get_authorization_conditions(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> AuthorizationConditionsResult:
        key = (resource_type, action)
        return self.conditions.get(
            key,
            AuthorizationConditionsResult(filter_type="denied_all"),
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
            auth_context,
            role_names,
        )
        if conditions.granted_all:
            return AuthorizationFilter.grant_all()
        if conditions.denied_all:
            return AuthorizationFilter.deny_all()
        return AuthorizationFilter.deny_all()

    async def list_resource_types(self) -> list[str]:
        return list({k[0] for k in self.allowed_ids})

    async def list_actions(self, resource_type: str) -> list[str]:
        return list({k[1] for k in self.allowed_ids if k[0] == resource_type})


# ---------------------------------------------------------------------------
# Stub: IAuthorizationAdminPort
# ---------------------------------------------------------------------------


class StubAuthorizationAdminPort:
    """In-memory stub for IAuthorizationAdminPort."""

    def __init__(self) -> None:
        self.resource_types: dict[str, dict[str, Any]] = {}
        self.actions: dict[str, dict[str, Any]] = {}
        self.resources: dict[tuple[str, str], dict[str, Any]] = {}
        self.acls: list[dict[str, Any]] = []
        self._next_id = 1

    async def create_resource_type(
        self, name: str, *, is_public: bool = False
    ) -> dict[str, Any]:
        self.resource_types[name] = {"name": name, "is_public": is_public}
        return self.resource_types[name]

    async def list_resource_types(self) -> list[dict[str, Any]]:
        return list(self.resource_types.values())

    async def delete_resource_type(self, name: str) -> dict[str, Any]:
        return self.resource_types.pop(name, {"deleted": True})

    async def set_resource_type_public(
        self, name: str, is_public: bool
    ) -> dict[str, Any]:
        prev = self.resource_types.get(name, {}).get("is_public", False)
        if name in self.resource_types:
            self.resource_types[name]["is_public"] = is_public
        return {"name": name, "is_public": is_public, "previous_public": prev}

    async def create_action(self, name: str) -> dict[str, Any]:
        self.actions[name] = {"name": name}
        return self.actions[name]

    async def list_actions(self) -> list[dict[str, Any]]:
        return list(self.actions.values())

    async def delete_action(self, name: str) -> dict[str, Any]:
        return self.actions.pop(name, {"deleted": True})

    async def register_resource(
        self,
        resource_type: str,
        resource_id: str,
        attributes: dict[str, Any] | None = None,
        geometry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = (resource_type, resource_id)
        self.resources[key] = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            **(attributes or {}),
        }
        return self.resources[key]

    async def sync_resources(
        self, resource_type: str, resources: list[dict[str, Any]]
    ) -> dict[str, Any]:
        for r in resources:
            rid = r.get("external_id", r.get("id", ""))
            self.resources[(resource_type, str(rid))] = r
        return {"synced": len(resources)}

    async def delete_resource(
        self, resource_type: str, resource_id: str
    ) -> dict[str, Any]:
        self.resources.pop((resource_type, resource_id), None)
        return {"deleted": True}

    async def create_acl(
        self,
        resource_type: str | None = None,
        action: str | None = None,
        *,
        principal_name: str | None = None,
        role_name: str | None = None,
        resource_external_id: str | None = None,
        conditions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        acl = {
            "id": self._next_id,
            "resource_type": resource_type,
            "action": action,
            "principal_name": principal_name,
            "role_name": role_name,
            "resource_external_id": resource_external_id,
            "conditions": conditions,
        }
        self._next_id += 1
        self.acls.append(acl)
        return acl

    async def create_acl_from_specification(
        self,
        resource_type: str,
        action: str,
        *,
        principal_name: str | None = None,
        role_name: str | None = None,
        resource_external_id: str | None = None,
        specification_dsl: dict[str, Any],
        field_mapping: FieldMapping | None = None,
    ) -> dict[str, Any]:
        return await self.create_acl(
            resource_type,
            action,
            principal_name=principal_name,
            role_name=role_name,
            resource_external_id=resource_external_id,
            conditions=specification_dsl,
        )

    async def list_acls(
        self,
        resource_type: str | None = None,
        action: str | None = None,
        principal_name: str | None = None,
        role_name: str | None = None,
    ) -> list[dict[str, Any]]:
        result = self.acls
        if resource_type:
            result = [a for a in result if a.get("resource_type") == resource_type]
        if action:
            result = [a for a in result if a.get("action") == action]
        return result

    async def delete_acl(self, acl_id: int | str) -> dict[str, Any]:
        self.acls = [a for a in self.acls if a.get("id") != int(acl_id)]
        return {"deleted": True}

    async def delete_acl_by_key(
        self,
        resource_type: str,
        action: str,
        *,
        principal_name: str | None = None,
        role_name: str | None = None,
        resource_external_id: str | None = None,
    ) -> dict[str, Any]:
        before = len(self.acls)
        self.acls = [
            a
            for a in self.acls
            if not (
                a.get("resource_type") == resource_type
                and a.get("action") == action
                and a.get("principal_name") == principal_name
                and a.get("role_name") == role_name
            )
        ]
        return {"deleted": before != len(self.acls), "previous_state": {}}

    async def list_principals(self) -> list[dict[str, Any]]:
        return []

    async def list_roles(self) -> list[dict[str, Any]]:
        return []

    async def ensure_realm(
        self, idp_config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"provisioned": True}

    async def sync_realm(self) -> dict[str, Any]:
        return {"synced": True}


# ---------------------------------------------------------------------------
# Stub: IOwnershipResolver
# ---------------------------------------------------------------------------


class StubOwnershipResolver:
    def __init__(
        self, owners: dict[tuple[str, str], str | list[str]] | None = None
    ) -> None:
        self._owners = owners or {}

    async def get_owner(
        self, resource_type: str, resource_id: str
    ) -> str | list[str] | None:
        return self._owners.get((resource_type, resource_id))


# ---------------------------------------------------------------------------
# Stub: IPermissionCache
# ---------------------------------------------------------------------------


class StubPermissionCache:
    def __init__(self) -> None:
        self._store: dict[str, AuthorizationDecision] = {}

    async def get(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str | None,
        action: str,
    ) -> AuthorizationDecision | None:
        key = f"{principal_id}:{resource_type}:{resource_id}:{action}"
        return self._store.get(key)

    async def set(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str | None,
        action: str,
        decision: AuthorizationDecision,
        ttl: int | None = None,
    ) -> None:
        key = f"{principal_id}:{resource_type}:{resource_id}:{action}"
        self._store[key] = decision

    async def invalidate(
        self, resource_type: str, resource_id: str | None = None
    ) -> None:
        prefix = (
            f":{resource_type}:{resource_id}:" if resource_id else f":{resource_type}:"
        )
        self._store = {k: v for k, v in self._store.items() if prefix not in k}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def principal() -> Principal:
    return Principal(
        user_id="user-1",
        username="testuser",
        roles={"user", "editor"},
        permissions={"order:read", "order:write"},
    )


@pytest.fixture
def admin_principal() -> Principal:
    return Principal(
        user_id="admin-1",
        username="adminuser",
        roles={"admin", "superadmin"},
        permissions=set(),
    )


@pytest.fixture
def anonymous_principal() -> Principal:
    return Principal(
        user_id="anon",
        username="anonymous",
        roles=set(),
        permissions=set(),
    )


@pytest.fixture
def stub_auth_port() -> StubAuthorizationPort:
    return StubAuthorizationPort()


@pytest.fixture
def stub_admin_port() -> StubAuthorizationAdminPort:
    return StubAuthorizationAdminPort()


@pytest.fixture
def stub_ownership_resolver() -> StubOwnershipResolver:
    return StubOwnershipResolver()


@pytest.fixture
def stub_cache() -> StubPermissionCache:
    return StubPermissionCache()
