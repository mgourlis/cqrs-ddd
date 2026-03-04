"""StatefulABACAdminAdapter — IAuthorizationAdminPort via stateful-abac-sdk."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...ports import IAuthorizationAdminPort
from .condition_converter import ConditionConverter

if TYPE_CHECKING:
    from ...models import FieldMapping
    from .config import ABACClientConfig

logger = logging.getLogger(__name__)


class StatefulABACAdminAdapter(IAuthorizationAdminPort):
    """Administrative ABAC management via stateful-abac-policy-engine.

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
            )
        return self._clients[realm]

    # ── Resource type lifecycle ──────────────────────────────────

    async def create_resource_type(
        self, name: str, *, is_public: bool = False
    ) -> dict[str, Any]:
        client = self._get_client()
        result = await client.resource_types.create(name=name, is_public=is_public)
        return result.__dict__ if hasattr(result, "__dict__") else dict(result)

    async def list_resource_types(self) -> list[dict[str, Any]]:
        client = self._get_client()
        types = await client.resource_types.list()
        return [t.__dict__ if hasattr(t, "__dict__") else dict(t) for t in types]

    async def delete_resource_type(self, name: str) -> dict[str, Any]:
        client = self._get_client()
        result = await client.resource_types.delete(name=name)
        out = {"deleted": True, "name": name}
        return result if isinstance(result, dict) else out

    async def set_resource_type_public(
        self, name: str, is_public: bool
    ) -> dict[str, Any]:
        # Not yet supported by stateful-abac-policy-engine
        raise NotImplementedError(
            "set_resource_type_public is not yet implemented in "
            "stateful-abac-policy-engine"
        )

    # ── Action lifecycle ─────────────────────────────────────────

    async def create_action(self, name: str) -> dict[str, Any]:
        client = self._get_client()
        result = await client.actions.create(name=name)
        return result.__dict__ if hasattr(result, "__dict__") else dict(result)

    async def list_actions(self) -> list[dict[str, Any]]:
        client = self._get_client()
        actions = await client.actions.list()
        return [a.__dict__ if hasattr(a, "__dict__") else dict(a) for a in actions]

    async def delete_action(self, name: str) -> dict[str, Any]:
        client = self._get_client()
        result = await client.actions.delete(name=name)
        return result if isinstance(result, dict) else {"deleted": True, "name": name}

    # ── Resource registration ────────────────────────────────────

    async def register_resource(
        self,
        resource_type: str,
        resource_id: str,
        attributes: dict[str, Any] | None = None,
        geometry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from stateful_abac_sdk.models import Resource

        client = self._get_client()
        resource = Resource(
            external_id=resource_id,
            resource_type_name=resource_type,
            attributes=attributes or {},
            geometry=geometry,
        )
        resources = [resource]
        result = await client.resources.sync(resources)
        return result if isinstance(result, dict) else {"synced": True}

    async def sync_resources(
        self,
        resource_type: str,  # noqa: ARG002 - required by protocol
        resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from stateful_abac_sdk.models import Resource

        client = self._get_client()
        sdk_resources = [
            Resource(
                external_id=r.get("external_id", r.get("id", "")),
                resource_type_name=resource_type,
                attributes={
                    k: v
                    for k, v in r.items()
                    if k not in ("external_id", "id", "geometry")
                },
                geometry=r.get("geometry"),
            )
            for r in resources
        ]
        result = await client.resources.sync(sdk_resources)
        return result if isinstance(result, dict) else {"synced": len(resources)}

    async def delete_resource(
        self, _resource_type: str, resource_id: str
    ) -> dict[str, Any]:
        client = self._get_client()
        result = await client.resources.batch_update(
            delete=[resource_id],
        )
        return result if isinstance(result, dict) else {"deleted": True}

    # ── ACL CRUD ─────────────────────────────────────────────────

    async def create_acl(
        self,
        resource_type: str | None = None,  # noqa: ARG002
        action: str | None = None,
        *,
        principal_name: str | None = None,
        role_name: str | None = None,
        resource_external_id: str | None = None,
        conditions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        result = await client.acls.create(
            resource_type_name=resource_type,
            action_name=action,
            principal_name=principal_name,
            role_name=role_name,
            resource_external_id=resource_external_id,
            conditions=conditions,
        )
        return result.__dict__ if hasattr(result, "__dict__") else dict(result)

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
        # Convert specification DSL to ABAC conditions
        conditions = specification_dsl
        if field_mapping:
            converter = ConditionConverter(field_mapping)
            from cqrs_ddd_specifications import SpecificationFactory
            from cqrs_ddd_specifications.operators_memory import build_default_registry

            spec: Any = SpecificationFactory.from_dict(
                specification_dsl, registry=build_default_registry()
            )
            conditions = converter.specification_to_dsl(spec)

        return await self.create_acl(
            resource_type=resource_type,
            action=action,
            principal_name=principal_name,
            role_name=role_name,
            resource_external_id=resource_external_id,
            conditions=conditions,
        )

    async def list_acls(
        self,
        resource_type: str | None = None,
        action: str | None = None,
        principal_name: str | None = None,
        role_name: str | None = None,
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        acls = await client.acls.list(
            resource_type_name=resource_type,
            action_name=action,
            principal_name=principal_name,
            role_name=role_name,
        )
        return [a.__dict__ if hasattr(a, "__dict__") else dict(a) for a in acls]

    async def delete_acl(self, acl_id: int | str) -> dict[str, Any]:
        client = self._get_client()
        result = await client.acls.delete(acl_id=int(acl_id))
        return result.__dict__ if hasattr(result, "__dict__") else {"deleted": True}

    async def delete_acl_by_key(
        self,
        resource_type: str,
        action: str,
        *,
        principal_name: str | None = None,
        role_name: str | None = None,
        resource_external_id: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        result = await client.acls.delete_by_key(
            resource_type_name=resource_type,
            action_name=action,
            principal_name=principal_name,
            role_name=role_name,
            resource_external_id=resource_external_id,
        )
        return result.__dict__ if hasattr(result, "__dict__") else {"deleted": True}

    # ── Principal/Role listing ───────────────────────────────────

    async def list_principals(self) -> list[dict[str, Any]]:
        client = self._get_client()
        principals = await client.principals.list()
        return [p.__dict__ if hasattr(p, "__dict__") else dict(p) for p in principals]

    async def list_roles(self) -> list[dict[str, Any]]:
        client = self._get_client()
        roles = await client.roles.list()
        return [r.__dict__ if hasattr(r, "__dict__") else dict(r) for r in roles]

    # ── Realm provisioning ───────────────────────────────────────

    async def ensure_realm(
        self,
        idp_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Provision realm, ``elevation`` resource type, and ``admin`` action."""
        client = self._get_client()

        # Create/ensure the realm
        try:
            realm_result = await client.realms.create(
                name=self._config.resolve_realm(),
                idp_config=idp_config,
            )
        except Exception:  # noqa: BLE001 - realm may already exist
            logger.debug("Realm may already exist: %s", self._config.resolve_realm())
            realm_result = {"name": self._config.resolve_realm()}

        # Ensure "elevation" resource type (for step-up auth)
        try:
            await client.resource_types.create(name="elevation")
        except Exception:  # noqa: BLE001 - resource type may already exist
            logger.debug("elevation resource type may already exist")

        # Ensure "admin" action
        try:
            await client.actions.create(name="admin")
        except Exception:  # noqa: BLE001 - action may already exist
            logger.debug("admin action may already exist")

        return realm_result if isinstance(realm_result, dict) else {"provisioned": True}

    async def sync_realm(self) -> dict[str, Any]:
        client = self._get_client()
        try:
            result = await client.realms.sync()
            return result if isinstance(result, dict) else {"synced": True}
        except Exception as exc:  # noqa: BLE001 - sync may fail for many reasons
            logger.warning("Realm sync failed: %s", exc)
            return {"synced": False, "error": str(exc)}
