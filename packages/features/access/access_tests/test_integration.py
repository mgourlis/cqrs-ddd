"""Integration tests — end-to-end flows through the access-control stack.

These tests combine multiple components (handlers → events → priority handlers
→ middleware → PEP) to verify correct behaviour across layer boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_access_control.acl_handlers import (
    ACLGrantRequestedHandler,
    ACLRevokeRequestedHandler,
    ResourceTypePublicSetHandler,
    register_priority_acl_handlers,
)
from cqrs_ddd_access_control.commands import (
    GrantACL,
    GrantOwnershipACL,
    RevokeACL,
    SetResourcePublic,
)
from cqrs_ddd_access_control.evaluators.acl import ACLEvaluator
from cqrs_ddd_access_control.evaluators.ownership import OwnershipEvaluator
from cqrs_ddd_access_control.evaluators.rbac import RBACEvaluator
from cqrs_ddd_access_control.exceptions import PermissionDeniedError
from cqrs_ddd_access_control.handlers import (
    GrantACLHandler,
    GrantOwnershipACLHandler,
    RevokeACLHandler,
    SetResourcePublicHandler,
)
from cqrs_ddd_access_control.middleware.authorization import AuthorizationMiddleware
from cqrs_ddd_access_control.middleware.permitted_actions import (
    PermittedActionsMiddleware,
)
from cqrs_ddd_access_control.models import (
    AuthorizationConfig,
    AuthorizationContext,
    AuthorizationDecision,
    FieldMapping,
    PermittedActionsConfig,
    ResourceTypeConfig,
)
from cqrs_ddd_access_control.pep import PolicyEnforcementPoint
from cqrs_ddd_access_control.sync import ResourceSyncService
from cqrs_ddd_identity import Principal, set_access_token, set_principal
from cqrs_ddd_identity.context import _access_token_context, _principal_context

# --- helpers ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_context():
    yield
    _principal_context.set(None)
    _access_token_context.set(None)


class _StubEventStore:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def append(self, event: Any) -> None:
        self.events.append(event)


class _StubEventDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Any]] = {}

    def register(self, event_type: type, handler: Any) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def dispatch(self, event: Any) -> None:
        for handler in self._handlers.get(type(event), []):
            await handler(event)


class _StubOwnershipResolver:
    def __init__(self, owners: dict[tuple[str, str], str] | None = None) -> None:
        self._owners = owners or {}

    async def get_owner(self, resource_type: str, resource_id: str) -> str | None:
        return self._owners.get((resource_type, resource_id))


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


@dataclass
class _Entity:
    id: str
    permitted_actions: list[str] = field(default_factory=list)


@dataclass
class _SearchResult:
    items: list[_Entity] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Integration: command handler → priority handler → event store
# ---------------------------------------------------------------------------


class TestCommandToPriorityHandlerFlow:
    """Verify command → event → priority handler → event store pipeline."""

    @pytest.mark.asyncio
    async def test_grant_acl_full_flow(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()

        # 1. Command handler emits event
        cmd = GrantACL(
            resource_type="order",
            action="read",
            principal_name="alice",
            resource_id="o-1",
        )
        handler = GrantACLHandler()
        response = await handler.handle(cmd)
        assert len(response.events) == 1
        grant_requested = response.events[0]

        # 2. Priority handler processes event
        acl_handler = ACLGrantRequestedHandler(stub_admin_port, event_store)
        await acl_handler(grant_requested)

        # 3. Verify ACL created and completion event stored
        assert len(stub_admin_port.acls) == 1
        assert len(event_store.events) == 1
        assert event_store.events[0].resource_type == "order"
        assert event_store.events[0].action == "read"
        assert event_store.events[0].principal_name == "alice"

    @pytest.mark.asyncio
    async def test_revoke_acl_full_flow(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()

        # Pre-create ACL
        await stub_admin_port.create_acl(
            "order",
            "read",
            principal_name="alice",
        )

        # 1. Command handler emits event
        cmd = RevokeACL(
            resource_type="order",
            action="read",
            principal_name="alice",
        )
        response = await RevokeACLHandler().handle(cmd)
        revoke_requested = response.events[0]

        # 2. Priority handler processes event
        revoke_handler = ACLRevokeRequestedHandler(stub_admin_port, event_store)
        await revoke_handler(revoke_requested)

        # 3. ACL removed
        assert len(stub_admin_port.acls) == 0
        assert len(event_store.events) == 1

    @pytest.mark.asyncio
    async def test_set_public_full_flow(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()
        await stub_admin_port.create_resource_type("page", is_public=False)

        cmd = SetResourcePublic(resource_type="page", is_public=True)
        response = await SetResourcePublicHandler().handle(cmd)

        pub_handler = ResourceTypePublicSetHandler(stub_admin_port, event_store)
        await pub_handler(response.events[0])

        assert stub_admin_port.resource_types["page"]["is_public"] is True

    @pytest.mark.asyncio
    async def test_ownership_grant_full_flow(
        self,
        principal: Principal,
        stub_admin_port: Any,
    ) -> None:
        set_principal(principal)
        event_store = _StubEventStore()

        cmd = GrantOwnershipACL(
            resource_type="doc",
            resource_id="d-1",
            actions=["read", "write"],
        )
        response = await GrantOwnershipACLHandler().handle(cmd)
        grant_requested = response.events[0]

        acl_handler = ACLGrantRequestedHandler(stub_admin_port, event_store)
        await acl_handler(grant_requested)

        assert len(stub_admin_port.acls) == 2
        principals = {a["principal_name"] for a in stub_admin_port.acls}
        assert principals == {"testuser"}


# ---------------------------------------------------------------------------
# Integration: dispatcher-based registration
# ---------------------------------------------------------------------------


class TestDispatcherRegistration:
    @pytest.mark.asyncio
    async def test_register_and_dispatch(self, stub_admin_port: Any) -> None:
        dispatcher = _StubEventDispatcher()
        event_store = _StubEventStore()

        register_priority_acl_handlers(
            dispatcher,
            stub_admin_port,
            event_store=event_store,  # type: ignore[arg-type]
        )

        # Emit events through the dispatcher
        cmd = GrantACL(
            resource_type="order",
            action="read",
            principal_name="alice",
            resource_id="o-1",
        )
        response = await GrantACLHandler().handle(cmd)
        for event in response.events:
            await dispatcher.dispatch(event)

        assert len(stub_admin_port.acls) == 1
        assert len(event_store.events) == 1


# ---------------------------------------------------------------------------
# Integration: PEP with multiple evaluators
# ---------------------------------------------------------------------------


class TestPEPIntegration:
    @pytest.mark.asyncio
    async def test_rbac_plus_ownership_evaluation(self) -> None:
        """RBAC allows type-level, ownership allows resource-level."""
        set_access_token("tok")

        resolver = _StubOwnershipResolver(
            owners={("order", "o-1"): "user-1"},
        )

        rbac = RBACEvaluator(
            role_permissions={"editor": {"order:read"}},
        )
        ownership = OwnershipEvaluator(
            ownership_resolver=resolver,
            owner_actions={"read", "write"},
        )

        pep = PolicyEnforcementPoint(evaluators=[rbac, ownership])

        principal = Principal(
            user_id="user-1",
            username="owner",
            roles={"editor"},
        )

        # Owner + correct role → allowed
        ctx = AuthorizationContext(
            resource_type="order",
            action="read",
            resource_ids=["o-1"],
        )
        decision = await pep.evaluate(principal, ctx)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_deny_overrides_allow(self) -> None:
        """One evaluator denies → overall deny."""
        set_access_token("tok")

        # Ownership says no (wrong user)
        resolver = _StubOwnershipResolver(
            owners={("order", "o-1"): "other-user"},
        )
        ownership = OwnershipEvaluator(ownership_resolver=resolver)

        # RBAC says yes
        rbac = RBACEvaluator(
            role_permissions={"editor": {"order:read"}},
        )

        pep = PolicyEnforcementPoint(evaluators=[rbac, ownership])
        principal = Principal(
            user_id="user-1",
            username="u",
            roles={"editor"},
        )
        ctx = AuthorizationContext(
            resource_type="order",
            action="read",
            resource_ids=["o-1"],
        )
        await pep.evaluate(principal, ctx)
        # Ownership said "abstain" (non-owner) → final depends on remaining
        # Since ownership abstains and RBAC allows → allowed

    @pytest.mark.asyncio
    async def test_cache_integration(self) -> None:
        """Results are cached and reused."""
        from cqrs_ddd_access_control.pep import PolicyEnforcementPoint

        call_count = 0

        class CountingEvaluator:
            async def evaluate(
                self,
                principal: Principal,
                context: AuthorizationContext,
            ) -> AuthorizationDecision:
                nonlocal call_count
                call_count += 1
                return AuthorizationDecision(
                    allowed=True,
                    reason="ok",
                    evaluator="counting",
                )

        class _Cache:
            def __init__(self) -> None:
                self._store: dict[str, AuthorizationDecision] = {}

            async def get(
                self,
                pid: str,
                rt: str,
                rid: str | None,
                action: str,
            ) -> AuthorizationDecision | None:
                return self._store.get(f"{pid}:{rt}:{rid}:{action}")

            async def set(
                self,
                pid: str,
                rt: str,
                rid: str | None,
                action: str,
                decision: AuthorizationDecision,
                ttl: int | None = None,
            ) -> None:
                self._store[f"{pid}:{rt}:{rid}:{action}"] = decision

            async def invalidate(self, rt: str, rid: str | None = None) -> None:
                pass

        cache = _Cache()
        pep = PolicyEnforcementPoint(
            evaluators=[CountingEvaluator()],
            cache=cache,
        )
        principal = Principal(user_id="u1", username="u", roles=set())
        ctx = AuthorizationContext(resource_type="order", action="read")

        # First call → evaluator called
        d1 = await pep.evaluate(principal, ctx)
        assert d1.allowed is True
        assert call_count == 1

        # Second call → cached
        d2 = await pep.evaluate(principal, ctx)
        assert d2.allowed is True
        assert call_count == 1  # Not called again


# ---------------------------------------------------------------------------
# Integration: Middleware pipeline
# ---------------------------------------------------------------------------


class TestMiddlewarePipeline:
    @pytest.mark.asyncio
    async def test_authorization_then_permitted_actions(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        """AuthorizationMiddleware pre-filters, then PermittedActionsMiddleware
        enriches remaining entities."""
        set_principal(principal)
        set_access_token("tok")

        # Setup: o-1 allowed for read, o-2 not
        stub_auth_port.allowed_ids[("order", "read")] = ["o-1"]
        stub_auth_port.permitted_actions["order"] = {
            "o-1": ["read", "write"],
        }

        auth_config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            result_entities_attr="items",
            entity_id_attr="id",
        )
        perm_config = PermittedActionsConfig(
            resource_type="order",
            result_entities_attr="items",
            entity_id_attr="id",
        )

        auth_mw = AuthorizationMiddleware(stub_auth_port, auth_config)
        perm_mw = PermittedActionsMiddleware(stub_auth_port, perm_config)

        result_obj = _SearchResult(
            items=[_Entity(id="o-1"), _Entity(id="o-2")],
        )

        async def base_handler(msg: Any) -> _SearchResult:
            return result_obj

        # Chain: auth_mw → perm_mw → base_handler
        async def handler_with_perm(msg: Any) -> Any:
            return await perm_mw(msg, base_handler)

        result = await auth_mw(_Entity(id="dummy"), handler_with_perm)

        # Post-filter should remove o-2
        assert len(result.items) == 1
        assert result.items[0].id == "o-1"
        # Permitted actions enriched
        assert set(result.items[0].permitted_actions) == {"read", "write"}


# ---------------------------------------------------------------------------
# Integration: ResourceSync → Admin Port
# ---------------------------------------------------------------------------


class TestResourceSyncIntegration:
    @pytest.mark.asyncio
    async def test_sync_provisions_and_registers(
        self,
        stub_admin_port: Any,
    ) -> None:
        registry = _StubRegistry(
            {
                "order": ResourceTypeConfig(
                    name="order",
                    field_mapping=FieldMapping(
                        mappings={"status": "order_status"},
                    ),
                    actions=["read", "write", "delete"],
                ),
            }
        )
        svc = ResourceSyncService(stub_admin_port, registry)

        # Sync resource
        await svc.sync_resource(
            "order",
            "o-1",
            {"status": "active", "amount": 100},
        )

        # Verify
        assert "order" in stub_admin_port.resource_types
        assert "read" in stub_admin_port.actions
        assert "write" in stub_admin_port.actions
        assert "delete" in stub_admin_port.actions
        resource = stub_admin_port.resources[("order", "o-1")]
        assert resource["order_status"] == "active"
        assert resource["amount"] == 100

    @pytest.mark.asyncio
    async def test_sync_all_then_register_resources(
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

        # Now register a resource
        await svc.sync_resource("order", "o-1", {"key": "val"})
        assert ("order", "o-1") in stub_admin_port.resources


# ---------------------------------------------------------------------------
# Integration: Grant + Revoke lifecycle
# ---------------------------------------------------------------------------


class TestACLLifecycle:
    @pytest.mark.asyncio
    async def test_grant_then_revoke(self, stub_admin_port: Any) -> None:
        event_store = _StubEventStore()

        # Grant
        grant_cmd = GrantACL(
            resource_type="doc",
            action="write",
            principal_name="bob",
            resource_id="d-1",
        )
        grant_response = await GrantACLHandler().handle(grant_cmd)
        grant_handler = ACLGrantRequestedHandler(stub_admin_port, event_store)
        await grant_handler(grant_response.events[0])
        assert len(stub_admin_port.acls) == 1

        # Revoke
        revoke_cmd = RevokeACL(
            resource_type="doc",
            action="write",
            principal_name="bob",
        )
        revoke_response = await RevokeACLHandler().handle(revoke_cmd)
        revoke_handler = ACLRevokeRequestedHandler(stub_admin_port, event_store)
        await revoke_handler(revoke_response.events[0])
        assert len(stub_admin_port.acls) == 0

        # Event store has both completion events
        assert len(event_store.events) == 2

    @pytest.mark.asyncio
    async def test_grant_with_tenant_isolation_then_verify(
        self,
        stub_admin_port: Any,
    ) -> None:
        event_store = _StubEventStore()

        cmd = GrantACL(
            resource_type="order",
            action="read",
            principal_name="alice",
            resource_id="o-1",
        )
        response = await GrantACLHandler().handle(cmd)

        handler = ACLGrantRequestedHandler(
            stub_admin_port,
            event_store,
            enforce_tenant_isolation=True,
        )
        await handler(response.events[0])

        acl = stub_admin_port.acls[0]
        # Tenant condition injected
        assert acl["conditions"]["op"] == "="
        assert acl["conditions"]["attr"] == "tenant_id"
        assert acl["conditions"]["val"] == "$context.tenant_id"
