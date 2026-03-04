"""Tests for evaluators and PolicyEnforcementPoint."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_access_control.evaluators.acl import ACLEvaluator
from cqrs_ddd_access_control.evaluators.ownership import OwnershipEvaluator
from cqrs_ddd_access_control.evaluators.rbac import RBACEvaluator
from cqrs_ddd_access_control.models import (
    AuthorizationContext,
    AuthorizationDecision,
    CheckAccessBatchResult,
    CheckAccessItem,
)
from cqrs_ddd_access_control.pep import PolicyEnforcementPoint
from cqrs_ddd_identity import Principal

# ---------------------------------------------------------------------------
# Inline stubs (minimal, test-specific)
# ---------------------------------------------------------------------------


class _StubAuthPort:
    """Minimal IAuthorizationPort stub for evaluator tests."""

    def __init__(self) -> None:
        self.allowed_ids: dict[tuple[str, str], list[str]] = {}

    async def check_access(
        self,
        access_token: str | None,
        resource_type: str,
        action: str,
        resource_ids: list[str] | None = None,
        auth_context: dict[str, Any] | None = None,
        role_names: list[str] | None = None,
    ) -> list[str]:
        return self.allowed_ids.get((resource_type, action), [])

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
                result.access_map.setdefault((item.resource_type, rid), set()).add(
                    item.action
                )
        return result


class _StubOwnershipResolver:
    def __init__(
        self, owners: dict[tuple[str, str], str | list[str]] | None = None
    ) -> None:
        self._owners = owners or {}

    async def get_owner(
        self, resource_type: str, resource_id: str
    ) -> str | list[str] | None:
        return self._owners.get((resource_type, resource_id))


class _StubPermissionCache:
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
        pass


# ---------------------------------------------------------------------------
# RBACEvaluator
# ---------------------------------------------------------------------------


class TestRBACEvaluator:
    @pytest.mark.asyncio
    async def test_allow_when_role_has_permission(self) -> None:
        evaluator = RBACEvaluator(
            role_permissions={"editor": {"order:read", "order:write"}},
        )
        principal = Principal(user_id="u1", username="u", roles={"editor"})
        ctx = AuthorizationContext(resource_type="order", action="read")
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_abstain_when_no_match(self) -> None:
        evaluator = RBACEvaluator(role_permissions={"editor": {"order:read"}})
        principal = Principal(user_id="u1", username="u", roles={"viewer"})
        ctx = AuthorizationContext(resource_type="order", action="write")
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.reason == "abstain"

    @pytest.mark.asyncio
    async def test_role_hierarchy_expansion(self) -> None:
        evaluator = RBACEvaluator(
            role_permissions={"editor": {"order:read"}},
            role_hierarchy={"admin": {"editor"}},
        )
        principal = Principal(user_id="u1", username="u", roles={"admin"})
        ctx = AuthorizationContext(resource_type="order", action="read")
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_hierarchy_transitive(self) -> None:
        evaluator = RBACEvaluator(
            role_permissions={"viewer": {"order:read"}},
            role_hierarchy={"admin": {"editor"}, "editor": {"viewer"}},
        )
        principal = Principal(user_id="u1", username="u", roles={"admin"})
        ctx = AuthorizationContext(resource_type="order", action="read")
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is True


# ---------------------------------------------------------------------------
# ACLEvaluator
# ---------------------------------------------------------------------------


class TestACLEvaluator:
    @pytest.mark.asyncio
    async def test_allow_when_id_returned(self) -> None:
        port = _StubAuthPort()
        port.allowed_ids[("order", "read")] = ["1", "2"]
        evaluator = ACLEvaluator(authorization_port=port)
        principal = Principal(user_id="u1", username="u", roles=set())
        ctx = AuthorizationContext(
            resource_type="order", action="read", resource_ids=["1"]
        )
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_deny_when_id_not_returned(self) -> None:
        port = _StubAuthPort()
        port.allowed_ids[("order", "read")] = ["2"]
        evaluator = ACLEvaluator(authorization_port=port)
        principal = Principal(user_id="u1", username="u", roles=set())
        ctx = AuthorizationContext(
            resource_type="order", action="read", resource_ids=["1"]
        )
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_type_level_allow(self) -> None:
        port = _StubAuthPort()
        port.allowed_ids[("order", "read")] = ["__type__"]
        evaluator = ACLEvaluator(authorization_port=port)
        principal = Principal(user_id="u1", username="u", roles=set())
        ctx = AuthorizationContext(resource_type="order", action="read")
        # No resource_ids → type-level check
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_type_level_denied(self) -> None:
        port = _StubAuthPort()
        # No allowed IDs at all
        evaluator = ACLEvaluator(authorization_port=port)
        principal = Principal(user_id="u1", username="u", roles=set())
        ctx = AuthorizationContext(resource_type="order", action="read")
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is False
        assert decision.reason == "abstain"

    @pytest.mark.asyncio
    async def test_partial_deny_shows_denied_ids(self) -> None:
        port = _StubAuthPort()
        port.allowed_ids[("order", "read")] = ["1"]
        evaluator = ACLEvaluator(authorization_port=port)
        principal = Principal(user_id="u1", username="u", roles=set())
        ctx = AuthorizationContext(
            resource_type="order", action="read", resource_ids=["1", "2"]
        )
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is False
        assert "2" in decision.reason


# ---------------------------------------------------------------------------
# OwnershipEvaluator
# ---------------------------------------------------------------------------


class TestOwnershipEvaluator:
    @pytest.mark.asyncio
    async def test_owner_allowed(self) -> None:
        resolver = _StubOwnershipResolver(owners={("order", "1"): "user-1"})
        evaluator = OwnershipEvaluator(
            ownership_resolver=resolver,
            owner_actions={"read", "write", "delete"},
        )
        principal = Principal(user_id="user-1", username="u", roles=set())
        ctx = AuthorizationContext(
            resource_type="order", action="read", resource_ids=["1"]
        )
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_non_owner_denied(self) -> None:
        resolver = _StubOwnershipResolver(owners={("order", "1"): "other-user"})
        evaluator = OwnershipEvaluator(ownership_resolver=resolver)
        principal = Principal(user_id="user-1", username="u", roles=set())
        ctx = AuthorizationContext(
            resource_type="order", action="read", resource_ids=["1"]
        )
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_action_not_in_owner_actions_abstains(self) -> None:
        resolver = _StubOwnershipResolver(owners={("order", "1"): "user-1"})
        evaluator = OwnershipEvaluator(
            ownership_resolver=resolver,
            owner_actions={"read"},
        )
        principal = Principal(user_id="user-1", username="u", roles=set())
        ctx = AuthorizationContext(
            resource_type="order", action="admin", resource_ids=["1"]
        )
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.reason == "abstain"

    @pytest.mark.asyncio
    async def test_no_resource_ids_abstains(self) -> None:
        resolver = _StubOwnershipResolver()
        evaluator = OwnershipEvaluator(ownership_resolver=resolver)
        principal = Principal(user_id="user-1", username="u", roles=set())
        ctx = AuthorizationContext(resource_type="order", action="read")
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.reason == "abstain"

    @pytest.mark.asyncio
    async def test_owner_is_list_of_owners(self) -> None:
        """Cover the isinstance(owner, list) path."""
        resolver = _StubOwnershipResolver(owners={("order", "1"): ["user-1", "user-2"]})
        evaluator = OwnershipEvaluator(ownership_resolver=resolver)
        principal = Principal(user_id="user-1", username="u", roles=set())
        ctx = AuthorizationContext(
            resource_type="order", action="read", resource_ids=["1"]
        )
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_owner_list_not_containing_principal(self) -> None:
        resolver = _StubOwnershipResolver(
            owners={("order", "1"): ["other-1", "other-2"]}
        )
        evaluator = OwnershipEvaluator(ownership_resolver=resolver)
        principal = Principal(user_id="user-1", username="u", roles=set())
        ctx = AuthorizationContext(
            resource_type="order", action="read", resource_ids=["1"]
        )
        decision = await evaluator.evaluate(principal, ctx)
        assert decision.allowed is False


# ---------------------------------------------------------------------------
# PolicyEnforcementPoint
# ---------------------------------------------------------------------------


class TestPolicyEnforcementPoint:
    @pytest.mark.asyncio
    async def test_bypass_roles(self) -> None:
        pep = PolicyEnforcementPoint(
            evaluators=[], bypass_roles=frozenset({"superadmin"})
        )
        principal = Principal(user_id="a1", username="admin", roles={"superadmin"})
        ctx = AuthorizationContext(resource_type="order", action="delete")
        decision = await pep.evaluate(principal, ctx)
        assert decision.allowed is True
        assert decision.reason == "Bypass role"

    @pytest.mark.asyncio
    async def test_deny_wins(self) -> None:
        port = _StubAuthPort()
        port.allowed_ids[("order", "read")] = []  # deny

        rbac = RBACEvaluator(role_permissions={"editor": {"order:read"}})
        acl = ACLEvaluator(authorization_port=port)

        pep = PolicyEnforcementPoint(evaluators=[rbac, acl])
        principal = Principal(user_id="u1", username="u", roles={"editor"})
        ctx = AuthorizationContext(
            resource_type="order", action="read", resource_ids=["1"]
        )
        decision = await pep.evaluate(principal, ctx)
        # ACL denies (resource_id "1" not in allowed list) → deny wins
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_first_allow_is_candidate(self) -> None:
        rbac = RBACEvaluator(role_permissions={"editor": {"order:read"}})
        pep = PolicyEnforcementPoint(evaluators=[rbac])
        principal = Principal(user_id="u1", username="u", roles={"editor"})
        ctx = AuthorizationContext(resource_type="order", action="read")
        decision = await pep.evaluate(principal, ctx)
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_no_evaluators_deny(self) -> None:
        pep = PolicyEnforcementPoint(evaluators=[])
        principal = Principal(user_id="u1", username="u", roles=set())
        ctx = AuthorizationContext(resource_type="order", action="read")
        decision = await pep.evaluate(principal, ctx)
        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        cache = _StubPermissionCache()
        cached_decision = AuthorizationDecision(
            allowed=True, reason="cached", evaluator="cache"
        )
        await cache.set("u1", "order", None, "read", cached_decision)

        pep = PolicyEnforcementPoint(evaluators=[], cache=cache)
        principal = Principal(user_id="u1", username="u", roles=set())
        ctx = AuthorizationContext(resource_type="order", action="read")
        decision = await pep.evaluate(principal, ctx)
        assert decision.allowed is True
        assert decision.reason == "cached"

    @pytest.mark.asyncio
    async def test_evaluate_batch(self) -> None:
        rbac = RBACEvaluator(role_permissions={"editor": {"order:read"}})
        pep = PolicyEnforcementPoint(evaluators=[rbac])
        principal = Principal(user_id="u1", username="u", roles={"editor"})
        contexts = [
            AuthorizationContext(resource_type="order", action="read"),
            AuthorizationContext(resource_type="order", action="delete"),
        ]
        decisions = await pep.evaluate_batch(principal, contexts)
        assert len(decisions) == 2
        assert decisions[0].allowed is True
        assert decisions[1].allowed is False
