"""ResourceSyncService — provision resources in the authorization engine."""

from __future__ import annotations

import logging
from typing import Any

from .ports import IAuthorizationAdminPort, IResourceTypeRegistry

logger = logging.getLogger(__name__)


class ResourceSyncService:
    """Provision resource types, actions, and resource instances.

    Mirrors ``ABACResourceSyncService`` from ``py-cqrs-ddd-auth``.

    Parameters
    ----------
    admin_port:
        Authorization admin port for CRUD operations.
    registry:
        Resource type registry for field mapping resolution.
    """

    def __init__(
        self,
        admin_port: IAuthorizationAdminPort,
        registry: IResourceTypeRegistry,
    ) -> None:
        self._admin_port = admin_port
        self._registry = registry
        self._provisioned: set[str] = set()

    async def ensure_resource_type(self, resource_type: str) -> None:
        """Create resource type and its actions in the authorization engine.

        Caches which types have been provisioned to avoid duplicate calls.
        """
        if resource_type in self._provisioned:
            return

        config = self._registry.get_config(resource_type)
        is_public = config.is_public if config else False

        await self._admin_port.create_resource_type(resource_type, is_public=is_public)

        if config and config.actions:
            for action in config.actions:
                try:
                    await self._admin_port.create_action(action)
                except Exception:  # noqa: BLE001 - action may already exist
                    logger.debug("Action %s may already exist", action)

        self._provisioned.add(resource_type)
        logger.info("Provisioned resource type: %s", resource_type)

    async def sync_resource(
        self,
        resource_type: str,
        resource_id: str,
        attributes: dict[str, Any],
        geometry: dict[str, Any] | None = None,
    ) -> None:
        """Transform attributes via FieldMapping and register/update in engine.

        Parameters
        ----------
        geometry:
            Optional GeoJSON for spatial ABAC conditions (PostGIS-backed).
        """
        await self.ensure_resource_type(resource_type)
        transformed = self.transform_attributes(resource_type, attributes)
        await self._admin_port.register_resource(
            resource_type, resource_id, attributes=transformed, geometry=geometry
        )

    async def delete_resource(self, resource_type: str, resource_id: str) -> None:
        """Delete a resource from the authorization engine."""
        await self._admin_port.delete_resource(resource_type, resource_id)

    def transform_attributes(
        self,
        resource_type: str,
        attributes: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply field mapping (app field names → ABAC attribute names)."""
        config = self._registry.get_config(resource_type)
        if not config or not config.field_mapping.mappings:
            return attributes

        mapping = config.field_mapping
        transformed: dict[str, Any] = {}
        for app_field, value in attributes.items():
            abac_attr = mapping.get_abac_attr(app_field)
            transformed[abac_attr] = value
        return transformed

    async def sync_all_resource_types(self) -> None:
        """Provision all registered resource types."""
        for resource_type in self._registry.list_types():
            await self.ensure_resource_type(resource_type)
