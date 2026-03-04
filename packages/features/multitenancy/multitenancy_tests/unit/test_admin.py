from datetime import datetime, timezone

import pytest

from cqrs_ddd_multitenancy.admin import (
    InMemoryTenantRegistry,
    TenantAdmin,
    TenantInfo,
    TenantStatus,
)
from cqrs_ddd_multitenancy.context import SYSTEM_TENANT, reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import (
    CrossTenantAccessError,
    TenantDeactivatedError,
    TenantNotFoundError,
    TenantProvisioningError,
)
from cqrs_ddd_multitenancy.isolation import IsolationConfig, TenantIsolationStrategy


def make_admin(registry=None, on_provision=None, on_deactivate=None):
    if registry is None:
        registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    return registry, TenantAdmin(
        registry=registry,
        config=config,
        on_provision=on_provision,
        on_deactivate=on_deactivate,
    )


@pytest.mark.asyncio
async def test_in_memory_registry():
    registry = InMemoryTenantRegistry()
    tenant = TenantInfo(tenant_id="t1", name="Tenant 1")

    await registry.save(tenant)
    assert await registry.get("t1") == tenant
    assert len(await registry.list_all()) == 1

    await registry.delete("t1")
    assert await registry.get("t1") is None


@pytest.mark.asyncio
async def test_in_memory_registry_list_all_includes_deactivated():
    registry = InMemoryTenantRegistry()
    active = TenantInfo(tenant_id="t1", name="T1", status=TenantStatus.ACTIVE)
    deactivated = TenantInfo(tenant_id="t2", name="T2", status=TenantStatus.DEACTIVATED)
    await registry.save(active)
    await registry.save(deactivated)

    # Default: exclude deactivated
    result = await registry.list_all()
    assert len(result) == 1

    # Include deactivated
    result_all = await registry.list_all(include_deactivated=True)
    assert len(result_all) == 2


@pytest.mark.asyncio
async def test_tenant_admin_provision():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    admin = TenantAdmin(registry=registry, config=config)

    token = set_tenant(SYSTEM_TENANT)
    try:
        tenant = await admin.provision_tenant(tenant_id="t1", name="T1")
        assert tenant.tenant_id == "t1"
        assert tenant.status == TenantStatus.ACTIVE

        saved = await registry.get("t1")
        assert saved is not None
        assert saved.name == "T1"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_provision_with_callback():
    called_with = []

    async def on_prov(tenant, session):
        called_with.append(tenant.tenant_id)

    registry, admin = make_admin(on_provision=on_prov)
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        assert "t1" in called_with
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_provision_duplicate_raises():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        with pytest.raises(TenantProvisioningError):
            await admin.provision_tenant("t1", "T1 again")
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_provision_deactivated_raises():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        await admin.deactivate_tenant("t1")
        # Provisioning a deactivated tenant should raise
        with pytest.raises(TenantProvisioningError):
            await admin.provision_tenant("t1", "T1 new")
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_provision_rollback_on_callback_failure():
    async def failing_callback(tenant, session):
        raise RuntimeError("provisioning failed")

    registry, admin = make_admin(on_provision=failing_callback)
    token = set_tenant(SYSTEM_TENANT)
    try:
        with pytest.raises(TenantProvisioningError):
            await admin.provision_tenant("t1", "T1")
        # Tenant should be rolled back
        assert await registry.get("t1") is None
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_provision_requires_system_tenant():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    admin = TenantAdmin(registry=registry, config=config)

    token = set_tenant("other-tenant")
    try:
        with pytest.raises(CrossTenantAccessError):
            await admin.provision_tenant(tenant_id="t1", name="T1")
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_deactivate_reactivate():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    admin = TenantAdmin(registry=registry, config=config)

    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant(tenant_id="t1", name="T1")

        await admin.deactivate_tenant("t1", reason="Billing")
        updated = await registry.get("t1")
        assert updated.status == TenantStatus.DEACTIVATED
        assert updated.deactivated_at is not None

        # Test reactivate
        await admin.reactivate_tenant("t1")
        restored = await registry.get("t1")
        assert restored.status == TenantStatus.ACTIVE
        assert restored.deactivated_at is None
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_deactivate_already_deactivated():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        await admin.deactivate_tenant("t1")
        # Deactivating again should return same tenant (no error)
        result = await admin.deactivate_tenant("t1")
        assert result.status == TenantStatus.DEACTIVATED
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_deactivate_with_callback():
    called_with = []

    async def on_deact(tenant):
        called_with.append(tenant.tenant_id)

    registry, admin = make_admin(on_deactivate=on_deact)
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        await admin.deactivate_tenant("t1")
        assert "t1" in called_with
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_deactivate_not_found():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    admin = TenantAdmin(registry=registry, config=config)

    token = set_tenant(SYSTEM_TENANT)
    try:
        with pytest.raises(TenantNotFoundError):
            await admin.deactivate_tenant("missing", reason="test")
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_reactivate_active_returns_tenant():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        # Reactivating an already-active tenant should return same tenant
        result = await admin.reactivate_tenant("t1")
        assert result.status == TenantStatus.ACTIVE
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_reactivate_not_found():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        with pytest.raises(TenantNotFoundError):
            await admin.reactivate_tenant("missing")
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_get_tenant():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        tenant = await admin.get_tenant("t1")
        assert tenant.tenant_id == "t1"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_get_tenant_not_found():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        with pytest.raises(TenantNotFoundError):
            await admin.get_tenant("missing")
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_get_tenant_deactivated_raises():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        await admin.deactivate_tenant("t1")
        with pytest.raises(TenantDeactivatedError):
            await admin.get_tenant("t1")
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_list_tenants():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        await admin.provision_tenant("t2", "T2")
        tenants = await admin.list_tenants()
        assert len(tenants) == 2
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_list_tenants_includes_deactivated():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        await admin.provision_tenant("t2", "T2")
        await admin.deactivate_tenant("t2")

        active = await admin.list_tenants()
        assert len(active) == 1

        all_tenants = await admin.list_tenants(include_deactivated=True)
        assert len(all_tenants) == 2
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_update_metadata_merge():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1", metadata={"key1": "val1"})
        updated = await admin.update_tenant_metadata("t1", {"key2": "val2"})
        assert updated.metadata["key1"] == "val1"
        assert updated.metadata["key2"] == "val2"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_update_metadata_no_merge():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1", metadata={"key1": "val1"})
        updated = await admin.update_tenant_metadata(
            "t1", {"key2": "val2"}, merge=False
        )
        assert "key1" not in updated.metadata
        assert updated.metadata["key2"] == "val2"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_update_metadata_not_found():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        with pytest.raises(TenantNotFoundError):
            await admin.update_tenant_metadata("missing", {"k": "v"})
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_delete_tenant():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        await admin.delete_tenant("t1")
        assert await registry.get("t1") is None
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_delete_tenant_with_callback():
    deleted = []

    async def on_del(tenant):
        deleted.append(tenant.tenant_id)

    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant("t1", "T1")
        await admin.delete_tenant("t1", on_delete=on_del)
        assert "t1" in deleted
        assert await registry.get("t1") is None
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_delete_tenant_not_found():
    registry, admin = make_admin()
    token = set_tenant(SYSTEM_TENANT)
    try:
        with pytest.raises(TenantNotFoundError):
            await admin.delete_tenant("missing")
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_properties():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    admin = TenantAdmin(registry=registry, config=config)

    assert admin.registry is registry
    assert admin.config is config


@pytest.mark.asyncio
async def test_in_memory_registry_standalone():
    registry = InMemoryTenantRegistry()
    tenant = TenantInfo(tenant_id="t1", name="Tenant 1")

    await registry.save(tenant)
    assert await registry.get("t1") == tenant
    assert len(await registry.list_all()) == 1

    await registry.delete("t1")
    assert await registry.get("t1") is None


@pytest.mark.asyncio
async def test_tenant_admin_provision_standalone():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    admin = TenantAdmin(registry=registry, config=config)

    token = set_tenant(SYSTEM_TENANT)
    try:
        tenant = await admin.provision_tenant(tenant_id="t1", name="T1")
        assert tenant.tenant_id == "t1"
        assert tenant.status == TenantStatus.ACTIVE

        saved = await registry.get("t1")
        assert saved is not None
        assert saved.name == "T1"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_provision_requires_system_tenant_standalone():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    admin = TenantAdmin(registry=registry, config=config)

    token = set_tenant("other-tenant")
    try:
        with pytest.raises(CrossTenantAccessError):
            await admin.provision_tenant(tenant_id="t1", name="T1")
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_deactivate_reactivate_standalone():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    admin = TenantAdmin(registry=registry, config=config)

    token = set_tenant(SYSTEM_TENANT)
    try:
        await admin.provision_tenant(tenant_id="t1", name="T1")

        await admin.deactivate_tenant("t1", reason="Billing")
        updated = await registry.get("t1")
        assert updated.status == TenantStatus.DEACTIVATED
        assert updated.deactivated_at is not None

        # Test reactivate
        await admin.reactivate_tenant("t1")
        restored = await registry.get("t1")
        assert restored.status == TenantStatus.ACTIVE
        assert restored.deactivated_at is None
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_tenant_admin_deactivate_not_found_standalone():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    admin = TenantAdmin(registry=registry, config=config)

    token = set_tenant(SYSTEM_TENANT)
    try:
        with pytest.raises(TenantNotFoundError):
            await admin.deactivate_tenant("missing", reason="test")
    finally:
        reset_tenant(token)
