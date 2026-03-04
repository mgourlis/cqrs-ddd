"""Tests for ResourceSyncService."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_access_control.models import FieldMapping, ResourceTypeConfig
from cqrs_ddd_access_control.sync import ResourceSyncService

# ---------------------------------------------------------------------------
# Stub IResourceTypeRegistry
# ---------------------------------------------------------------------------


class _StubRegistry:
    def __init__(self, configs: dict[str, ResourceTypeConfig] | None = None) -> None:
        self._configs = configs or {}

    def register(self, config: ResourceTypeConfig) -> None:
        self._configs[config.name] = config

    def get_config(self, resource_type: str) -> ResourceTypeConfig | None:
        return self._configs.get(resource_type)

    def get_config_for_entity(self, entity_cls: type) -> ResourceTypeConfig | None:
        return None

    def list_types(self) -> list[str]:
        return list(self._configs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResourceSyncService:
    @pytest.mark.asyncio
    async def test_ensure_resource_type_creates(
        self,
        stub_admin_port: Any,
    ) -> None:
        registry = _StubRegistry(
            {
                "order": ResourceTypeConfig(
                    name="order",
                    field_mapping=FieldMapping(),
                    actions=["read", "write"],
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)

        await svc.ensure_resource_type("order")

        assert "order" in stub_admin_port.resource_types
        assert "read" in stub_admin_port.actions
        assert "write" in stub_admin_port.actions

    @pytest.mark.asyncio
    async def test_ensure_resource_type_caches(
        self,
        stub_admin_port: Any,
    ) -> None:
        registry = _StubRegistry(
            {
                "order": ResourceTypeConfig(
                    name="order",
                    field_mapping=FieldMapping(),
                    actions=["read"],
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)

        await svc.ensure_resource_type("order")
        stub_admin_port.resource_types.clear()
        stub_admin_port.actions.clear()

        # Second call should be a no-op due to caching
        await svc.ensure_resource_type("order")
        assert "order" not in stub_admin_port.resource_types

    @pytest.mark.asyncio
    async def test_ensure_resource_type_unknown(
        self,
        stub_admin_port: Any,
    ) -> None:
        registry = _StubRegistry()  # empty
        svc = ResourceSyncService(stub_admin_port, registry)

        await svc.ensure_resource_type("unknown")
        # Resource type created even without registry config
        assert "unknown" in stub_admin_port.resource_types

    @pytest.mark.asyncio
    async def test_ensure_resource_type_public(
        self,
        stub_admin_port: Any,
    ) -> None:
        registry = _StubRegistry(
            {
                "page": ResourceTypeConfig(
                    name="page",
                    field_mapping=FieldMapping(),
                    is_public=True,
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)

        await svc.ensure_resource_type("page")
        assert stub_admin_port.resource_types["page"]["is_public"] is True

    @pytest.mark.asyncio
    async def test_sync_resource(
        self,
        stub_admin_port: Any,
    ) -> None:
        registry = _StubRegistry(
            {
                "order": ResourceTypeConfig(
                    name="order",
                    field_mapping=FieldMapping(mappings={"status": "order_status"}),
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)

        await svc.sync_resource("order", "o-1", {"status": "open"})

        # resource type should have been ensured
        assert "order" in stub_admin_port.resource_types
        # resource should be registered with transformed attrs
        resource = stub_admin_port.resources[("order", "o-1")]
        assert resource["order_status"] == "open"

    @pytest.mark.asyncio
    async def test_sync_resource_with_geometry(
        self,
        stub_admin_port: Any,
    ) -> None:
        registry = _StubRegistry(
            {
                "parcel": ResourceTypeConfig(
                    name="parcel",
                    field_mapping=FieldMapping(),
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)
        geo = {"type": "Point", "coordinates": [1.0, 2.0]}

        await svc.sync_resource("parcel", "p-1", {"area": 100}, geometry=geo)
        resource = stub_admin_port.resources[("parcel", "p-1")]
        assert resource is not None

    @pytest.mark.asyncio
    async def test_delete_resource(
        self,
        stub_admin_port: Any,
    ) -> None:
        stub_admin_port.resources[("order", "o-1")] = {"id": "o-1"}

        registry = _StubRegistry()
        svc = ResourceSyncService(stub_admin_port, registry)

        await svc.delete_resource("order", "o-1")
        assert ("order", "o-1") not in stub_admin_port.resources

    def test_transform_attributes_with_mapping(self, stub_admin_port: Any) -> None:
        registry = _StubRegistry(
            {
                "order": ResourceTypeConfig(
                    name="order",
                    field_mapping=FieldMapping(
                        mappings={"status": "order_status", "owner": "created_by"},
                    ),
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)

        result = svc.transform_attributes(
            "order",
            {"status": "open", "owner": "alice"},
        )
        assert result == {"order_status": "open", "created_by": "alice"}

    def test_transform_attributes_no_mapping(self, stub_admin_port: Any) -> None:
        registry = _StubRegistry(
            {
                "order": ResourceTypeConfig(
                    name="order",
                    field_mapping=FieldMapping(),
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)

        attrs = {"status": "open"}
        result = svc.transform_attributes("order", attrs)
        assert result == attrs

    def test_transform_attributes_unknown_type(self, stub_admin_port: Any) -> None:
        registry = _StubRegistry()
        svc = ResourceSyncService(stub_admin_port, registry)

        attrs = {"key": "value"}
        result = svc.transform_attributes("unknown", attrs)
        assert result == attrs

    @pytest.mark.asyncio
    async def test_sync_all_resource_types(
        self,
        stub_admin_port: Any,
    ) -> None:
        registry = _StubRegistry(
            {
                "order": ResourceTypeConfig(
                    name="order",
                    field_mapping=FieldMapping(),
                    actions=["read"],
                ),
                "doc": ResourceTypeConfig(
                    name="doc",
                    field_mapping=FieldMapping(),
                    actions=["read", "write"],
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)

        await svc.sync_all_resource_types()

        assert "order" in stub_admin_port.resource_types
        assert "doc" in stub_admin_port.resource_types

    @pytest.mark.asyncio
    async def test_action_creation_error_logged(
        self,
        stub_admin_port: Any,
    ) -> None:
        """If create_action raises (duplicate), it should be caught."""

        original_create = stub_admin_port.create_action
        call_count = 0

        async def failing_create(name: str) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("dup action")
            return await original_create(name)

        stub_admin_port.create_action = failing_create  # type: ignore[assignment]

        registry = _StubRegistry(
            {
                "order": ResourceTypeConfig(
                    name="order",
                    field_mapping=FieldMapping(),
                    actions=["read", "write"],
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)

        # Should not raise — error is caught and logged
        await svc.ensure_resource_type("order")
