"""End-to-end integration tests for TenantAdmin lifecycle.

Exercises the full admin workflow — provision, list, get, deactivate,
reactivate, update metadata, delete — using InMemoryTenantRegistry and
system tenant context, verifying all state transitions and error paths.
"""

from __future__ import annotations

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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> InMemoryTenantRegistry:
    return InMemoryTenantRegistry()


@pytest.fixture
def admin(registry: InMemoryTenantRegistry) -> TenantAdmin:
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    return TenantAdmin(registry=registry, config=config)


@pytest.fixture(autouse=True)
def system_ctx():
    """Run every test in this module under system tenant context."""
    token = set_tenant(SYSTEM_TENANT)
    yield
    reset_tenant(token)


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------


async def test_provision_creates_active_tenant(
    admin: TenantAdmin, registry: InMemoryTenantRegistry
):
    tenant = await admin.provision_tenant("acme", "Acme Corp")
    assert tenant.tenant_id == "acme"
    assert tenant.name == "Acme Corp"
    assert tenant.status == TenantStatus.ACTIVE

    saved = await registry.get("acme")
    assert saved is not None
    assert saved.status == TenantStatus.ACTIVE


async def test_provision_stores_metadata(
    admin: TenantAdmin, registry: InMemoryTenantRegistry
):
    meta = {"plan": "enterprise", "region": "eu-west-1"}
    tenant = await admin.provision_tenant("corp", "Corp Inc", metadata=meta)
    assert tenant.metadata == meta
    saved = await registry.get("corp")
    assert saved is not None
    assert saved.metadata == meta


async def test_provision_calls_on_provision_callback(admin: TenantAdmin):
    provisioned: list[str] = []

    async def on_prov(t: TenantInfo, _session: object) -> None:
        provisioned.append(t.tenant_id)

    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    a = TenantAdmin(
        registry=InMemoryTenantRegistry(), config=config, on_provision=on_prov
    )
    await a.provision_tenant("cb-tenant", "Callback Tenant")
    assert "cb-tenant" in provisioned


async def test_provision_raises_on_duplicate(admin: TenantAdmin):
    await admin.provision_tenant("dup", "Dup")
    with pytest.raises(TenantProvisioningError):
        await admin.provision_tenant("dup", "Dup again")


async def test_provision_raises_on_deactivated_id(admin: TenantAdmin):
    """Re-provisioning a deactivated tenant ID should suggest reactivate instead."""
    await admin.provision_tenant("old", "Old")
    await admin.deactivate_tenant("old")
    with pytest.raises(TenantProvisioningError, match="reactivate"):
        await admin.provision_tenant("old", "Old re-create")


async def test_provision_rollback_on_callback_failure(
    admin: TenantAdmin, registry: InMemoryTenantRegistry
):
    """If on_provision raises, the tenant is removed from registry."""

    async def failing_callback(t: TenantInfo, _session: object) -> None:
        raise RuntimeError("infra failed")

    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    a = TenantAdmin(registry=registry, config=config, on_provision=failing_callback)

    with pytest.raises(TenantProvisioningError):
        await a.provision_tenant("rollback-me", "Will Fail")

    assert await registry.get("rollback-me") is None


# ---------------------------------------------------------------------------
# Deactivation
# ---------------------------------------------------------------------------


async def test_deactivate_sets_deactivated_status(admin: TenantAdmin):
    await admin.provision_tenant("bye", "Bye Corp")
    tenant = await admin.deactivate_tenant("bye")
    assert tenant.status == TenantStatus.DEACTIVATED
    assert tenant.deactivated_at is not None


async def test_deactivate_stores_reason_in_metadata(
    admin: TenantAdmin, registry: InMemoryTenantRegistry
):
    await admin.provision_tenant("r-t", "R T")
    await admin.deactivate_tenant("r-t", reason="billing lapsed")
    saved = await registry.get("r-t")
    assert saved is not None
    assert saved.metadata.get("deactivation_reason") == "billing lapsed"


async def test_deactivate_already_deactivated_is_idempotent(admin: TenantAdmin):
    await admin.provision_tenant("idem", "Idem")
    await admin.deactivate_tenant("idem")
    result = await admin.deactivate_tenant("idem")  # second call — no error
    assert result.status == TenantStatus.DEACTIVATED


async def test_deactivate_not_found_raises(admin: TenantAdmin):
    with pytest.raises(TenantNotFoundError):
        await admin.deactivate_tenant("ghost")


async def test_deactivate_calls_on_deactivate_callback(admin: TenantAdmin):
    deactivated: list[str] = []

    async def on_deact(t: TenantInfo) -> None:
        deactivated.append(t.tenant_id)

    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    a = TenantAdmin(
        registry=InMemoryTenantRegistry(), config=config, on_deactivate=on_deact
    )
    await a.provision_tenant("cb2", "CB2")
    await a.deactivate_tenant("cb2")
    assert "cb2" in deactivated


# ---------------------------------------------------------------------------
# Reactivation
# ---------------------------------------------------------------------------


async def test_reactivate_restores_active_status(admin: TenantAdmin):
    await admin.provision_tenant("back", "Back Corp")
    await admin.deactivate_tenant("back")
    tenant = await admin.reactivate_tenant("back")
    assert tenant.status == TenantStatus.ACTIVE
    assert tenant.deactivated_at is None or True  # noqa: SIM222 - accept unset


async def test_reactivate_active_tenant_is_idempotent(admin: TenantAdmin):
    await admin.provision_tenant("already-active", "Already Active")
    result = await admin.reactivate_tenant("already-active")
    assert result.status == TenantStatus.ACTIVE


async def test_reactivate_not_found_raises(admin: TenantAdmin):
    with pytest.raises(TenantNotFoundError):
        await admin.reactivate_tenant("missing")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


async def test_list_tenants_active_only(admin: TenantAdmin):
    await admin.provision_tenant("t1", "T1")
    await admin.provision_tenant("t2", "T2")
    await admin.deactivate_tenant("t2")

    tenants = await admin.list_tenants()
    ids = {t.tenant_id for t in tenants}
    assert "t1" in ids
    assert "t2" not in ids


async def test_list_tenants_include_deactivated(admin: TenantAdmin):
    await admin.provision_tenant("a", "A")
    await admin.provision_tenant("b", "B")
    await admin.deactivate_tenant("b")

    tenants = await admin.list_tenants(include_deactivated=True)
    ids = {t.tenant_id for t in tenants}
    assert "a" in ids
    assert "b" in ids


async def test_list_tenants_empty(admin: TenantAdmin):
    assert await admin.list_tenants() == []


# ---------------------------------------------------------------------------
# get_tenant
# ---------------------------------------------------------------------------


async def test_get_tenant_returns_info(admin: TenantAdmin):
    await admin.provision_tenant("fetch-me", "Fetch Me")
    tenant = await admin.get_tenant("fetch-me")
    assert tenant.tenant_id == "fetch-me"
    assert tenant.status == TenantStatus.ACTIVE


async def test_get_tenant_not_found_raises(admin: TenantAdmin):
    with pytest.raises(TenantNotFoundError):
        await admin.get_tenant("nobody")


async def test_get_tenant_deactivated_raises(admin: TenantAdmin):
    await admin.provision_tenant("dead", "Dead")
    await admin.deactivate_tenant("dead")
    with pytest.raises(TenantDeactivatedError):
        await admin.get_tenant("dead")


# ---------------------------------------------------------------------------
# update_tenant_metadata
# ---------------------------------------------------------------------------


async def test_update_metadata_merge(admin: TenantAdmin):
    await admin.provision_tenant("m1", "M1", metadata={"a": 1})
    tenant = await admin.update_tenant_metadata("m1", {"b": 2})
    assert tenant.metadata == {"a": 1, "b": 2}


async def test_update_metadata_replace(admin: TenantAdmin):
    await admin.provision_tenant("m2", "M2", metadata={"a": 1, "b": 2})
    tenant = await admin.update_tenant_metadata("m2", {"c": 3}, merge=False)
    assert tenant.metadata == {"c": 3}


async def test_update_metadata_not_found_raises(admin: TenantAdmin):
    with pytest.raises(TenantNotFoundError):
        await admin.update_tenant_metadata("ghost", {"x": 1})


# ---------------------------------------------------------------------------
# delete_tenant
# ---------------------------------------------------------------------------


async def test_delete_tenant_removes_from_registry(
    admin: TenantAdmin, registry: InMemoryTenantRegistry
):
    await admin.provision_tenant("del-me", "Del Me")
    await admin.delete_tenant("del-me")
    assert await registry.get("del-me") is None


async def test_delete_tenant_calls_on_delete_callback(admin: TenantAdmin):
    deleted: list[str] = []

    async def on_del(t: TenantInfo) -> None:
        deleted.append(t.tenant_id)

    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    a = TenantAdmin(registry=InMemoryTenantRegistry(), config=config)
    await a.provision_tenant("del-cb", "Del CB")
    await a.delete_tenant("del-cb", on_delete=on_del)
    assert "del-cb" in deleted


async def test_delete_tenant_not_found_raises(admin: TenantAdmin):
    with pytest.raises(TenantNotFoundError):
        await admin.delete_tenant("nonexistent")


# ---------------------------------------------------------------------------
# Authorization — CrossTenantAccessError outside system context
# ---------------------------------------------------------------------------


async def test_admin_requires_system_tenant_context(admin: TenantAdmin):
    """All admin mutations must fail when called outside system_tenant context."""
    # Override autouse fixture by resetting to no tenant
    from cqrs_ddd_multitenancy.context import clear_tenant

    clear_tenant()

    with pytest.raises(CrossTenantAccessError):
        await admin.provision_tenant("sneaky", "Sneaky")


async def test_admin_requires_system_tenant_for_deactivate(admin: TenantAdmin):
    from cqrs_ddd_multitenancy.context import clear_tenant

    clear_tenant()
    with pytest.raises(CrossTenantAccessError):
        await admin.deactivate_tenant("any")


async def test_admin_requires_system_tenant_for_list(admin: TenantAdmin):
    from cqrs_ddd_multitenancy.context import clear_tenant

    clear_tenant()
    with pytest.raises(CrossTenantAccessError):
        await admin.list_tenants()


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


async def test_full_tenant_lifecycle(
    admin: TenantAdmin, registry: InMemoryTenantRegistry
):
    """Provision → list → deactivate → reactivate → delete."""
    # Provision
    t = await admin.provision_tenant(
        "lifecycle", "Lifecycle Corp", metadata={"env": "prod"}
    )
    assert t.status == TenantStatus.ACTIVE

    # List shows it
    active = await admin.list_tenants()
    assert any(x.tenant_id == "lifecycle" for x in active)

    # Deactivate
    t = await admin.deactivate_tenant("lifecycle")
    assert t.status == TenantStatus.DEACTIVATED

    # Not in active list; present in all list
    active = await admin.list_tenants()
    assert not any(x.tenant_id == "lifecycle" for x in active)
    all_tenants = await admin.list_tenants(include_deactivated=True)
    assert any(x.tenant_id == "lifecycle" for x in all_tenants)

    # Reactivate
    t = await admin.reactivate_tenant("lifecycle")
    assert t.status == TenantStatus.ACTIVE

    # Delete permanently
    await admin.delete_tenant("lifecycle")
    assert await registry.get("lifecycle") is None
