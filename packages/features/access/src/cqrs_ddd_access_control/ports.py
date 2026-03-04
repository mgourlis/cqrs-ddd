"""Access-control ports (protocols).

All protocols are ``@runtime_checkable``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .models import (
    AuthorizationConditionsResult,
    AuthorizationDecision,
    AuthorizationFilter,
    CheckAccessBatchResult,
    CheckAccessItem,
    FieldMapping,
    GetPermittedActionsItem,
    ResourceTypeConfig,
)

# ---------------------------------------------------------------------------
# Runtime authorization
# ---------------------------------------------------------------------------


@runtime_checkable
class IAuthorizationPort(Protocol):
    """Runtime authorization decisions — called by middleware."""

    async def check_access(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        resource_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> list[str]:
        """Return list of authorized resource IDs for the given action."""
        ...

    async def check_access_batch(
        self,
        access_token: str | None,
        items: list[CheckAccessItem],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> CheckAccessBatchResult:
        """Batch check: multiple resource-types/actions in one call."""
        ...

    async def get_permitted_actions(
        self,
        access_token: str | None,
        resource_type: str,
        resource_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Return which actions are permitted per resource."""
        ...

    async def get_permitted_actions_batch(
        self,
        access_token: str | None,
        items: list[GetPermittedActionsItem],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, dict[str, list[str]]]:
        """Batch: multiple resource types in one call."""
        ...

    async def get_type_level_permissions(
        self,
        access_token: str | None,
        resource_types: list[str],
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Per-resource-type action lists."""
        ...

    async def get_authorization_conditions(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> AuthorizationConditionsResult:
        """Return authorization conditions as DSL for single-query auth."""
        ...

    async def get_authorization_filter(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
        field_mapping: FieldMapping | None = None,
    ) -> AuthorizationFilter:
        """Conditions → specification-based filter for single-query auth."""
        ...

    async def list_resource_types(self) -> list[str]:
        """List all available resource types."""
        ...

    async def list_actions(self, resource_type: str) -> list[str]:
        """List all actions for a resource type."""
        ...


# ---------------------------------------------------------------------------
# Admin CRUD
# ---------------------------------------------------------------------------


@runtime_checkable
class IAuthorizationAdminPort(Protocol):
    """Administrative ABAC management — ACL CRUD, resource provisioning."""

    # Resource type lifecycle
    async def create_resource_type(
        self, name: str, *, is_public: bool = False
    ) -> dict[str, Any]: ...
    async def list_resource_types(self) -> list[dict[str, Any]]: ...
    async def delete_resource_type(self, name: str) -> dict[str, Any]: ...
    async def set_resource_type_public(
        self, name: str, is_public: bool
    ) -> dict[str, Any]: ...

    # Action lifecycle
    async def create_action(self, name: str) -> dict[str, Any]: ...
    async def list_actions(self) -> list[dict[str, Any]]: ...
    async def delete_action(self, name: str) -> dict[str, Any]: ...

    # Resource registration
    async def register_resource(
        self,
        resource_type: str,
        resource_id: str,
        attributes: dict[str, Any] | None = None,
        geometry: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    async def sync_resources(
        self,
        resource_type: str,
        resources: list[dict[str, Any]],
    ) -> dict[str, Any]: ...
    async def delete_resource(
        self, resource_type: str, resource_id: str
    ) -> dict[str, Any]: ...

    # ACL CRUD
    async def create_acl(
        self,
        resource_type: str | None = None,
        action: str | None = None,
        *,
        principal_name: str | None = None,
        role_name: str | None = None,
        resource_external_id: str | None = None,
        conditions: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

    async def list_acls(
        self,
        resource_type: str | None = None,
        action: str | None = None,
        principal_name: str | None = None,
        role_name: str | None = None,
    ) -> list[dict[str, Any]]: ...
    async def delete_acl(self, acl_id: int | str) -> dict[str, Any]: ...
    async def delete_acl_by_key(
        self,
        resource_type: str,
        action: str,
        *,
        principal_name: str | None = None,
        role_name: str | None = None,
        resource_external_id: str | None = None,
    ) -> dict[str, Any]: ...

    # Principal/Role listing
    async def list_principals(self) -> list[dict[str, Any]]: ...
    async def list_roles(self) -> list[dict[str, Any]]: ...

    # Realm provisioning
    async def ensure_realm(
        self,
        idp_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    async def sync_realm(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Ownership resolver
# ---------------------------------------------------------------------------


@runtime_checkable
class IOwnershipResolver(Protocol):
    """Application implements this to resolve resource owners."""

    async def get_owner(
        self,
        resource_type: str,
        resource_id: str,
    ) -> str | list[str] | None:
        """Return owner user_id(s) for a resource, or None if unknown."""
        ...


# ---------------------------------------------------------------------------
# Permission cache
# ---------------------------------------------------------------------------


@runtime_checkable
class IPermissionCache(Protocol):
    """Optional TTL-based cache for authorization decisions."""

    async def get(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str | None,
        action: str,
    ) -> AuthorizationDecision | None: ...

    async def set(
        self,
        principal_id: str,
        resource_type: str,
        resource_id: str | None,
        action: str,
        decision: AuthorizationDecision,
        ttl: int | None = None,
    ) -> None: ...

    async def invalidate(
        self, resource_type: str, resource_id: str | None = None
    ) -> None: ...


# ---------------------------------------------------------------------------
# Resource type registry
# ---------------------------------------------------------------------------


@runtime_checkable
class IResourceTypeRegistry(Protocol):
    """Registry of resource type configs populated by ``@register_access_entity``."""

    def register(self, config: ResourceTypeConfig) -> None: ...
    def get_config(self, resource_type: str) -> ResourceTypeConfig | None: ...
    def get_config_for_entity(self, entity_cls: type) -> ResourceTypeConfig | None: ...
    def list_types(self) -> list[str]: ...
