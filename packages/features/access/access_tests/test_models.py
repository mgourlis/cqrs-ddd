"""Tests for models, exceptions, and value objects."""

from __future__ import annotations

import pytest

from cqrs_ddd_access_control.exceptions import (
    AccessControlError,
    ACLError,
    ElevationRequiredError,
    InsufficientRoleError,
    PermissionDeniedError,
)
from cqrs_ddd_access_control.models import (
    AccessRule,
    AuthorizationConditionsResult,
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationFilter,
    CheckAccessBatchResult,
    FieldMapping,
    ResourceTypeConfig,
)


class TestAuthorizationContext:
    def test_frozen(self) -> None:
        ctx = AuthorizationContext(resource_type="order", action="read")
        with pytest.raises(AttributeError):
            ctx.action = "write"  # type: ignore[misc]

    def test_defaults(self) -> None:
        ctx = AuthorizationContext(resource_type="order", action="read")
        assert ctx.resource_ids is None
        assert ctx.resource_attributes == {}
        assert ctx.auth_context == {}


class TestAuthorizationDecision:
    def test_frozen(self) -> None:
        d = AuthorizationDecision(allowed=True, reason="ok", evaluator="test")
        assert d.allowed is True
        assert d.reason == "ok"

    def test_deny(self) -> None:
        d = AuthorizationDecision(allowed=False, reason="denied", evaluator="rbac")
        assert d.allowed is False


class TestCheckAccessBatchResult:
    def test_is_allowed_all(self) -> None:
        result = CheckAccessBatchResult(access_map={("order", "1"): {"read", "write"}})
        assert result.is_allowed(
            "order", "1", {"read", "write"}, action_quantifier="all"
        )
        assert not result.is_allowed(
            "order", "1", {"read", "delete"}, action_quantifier="all"
        )

    def test_is_allowed_any(self) -> None:
        result = CheckAccessBatchResult(access_map={("order", "1"): {"read"}})
        assert result.is_allowed(
            "order", "1", {"read", "write"}, action_quantifier="any"
        )
        assert not result.is_allowed("order", "1", {"delete"}, action_quantifier="any")

    def test_global_permissions(self) -> None:
        result = CheckAccessBatchResult(global_permissions={"read"})
        assert result.is_allowed("order", "999", {"read"})


class TestAuthorizationConditionsResult:
    def test_granted_all(self) -> None:
        r = AuthorizationConditionsResult(filter_type="granted_all")
        assert r.granted_all is True
        assert r.denied_all is False
        assert r.has_conditions is False

    def test_denied_all(self) -> None:
        r = AuthorizationConditionsResult(filter_type="denied_all")
        assert r.denied_all is True

    def test_conditions(self) -> None:
        r = AuthorizationConditionsResult(
            filter_type="conditions",
            conditions_dsl={"op": "=", "attr": "status", "val": "active"},
        )
        assert r.has_conditions is True


class TestAuthorizationFilter:
    def test_grant_all(self) -> None:
        f = AuthorizationFilter.grant_all()
        assert f.granted_all is True
        assert bool(f) is True

    def test_deny_all(self) -> None:
        f = AuthorizationFilter.deny_all()
        assert f.denied_all is True
        assert bool(f) is False

    def test_no_filter_is_falsy(self) -> None:
        f = AuthorizationFilter()
        assert bool(f) is False


class TestFieldMapping:
    def test_get_abac_attr(self) -> None:
        fm = FieldMapping(mappings={"status": "status_attr", "dept": "department"})
        assert fm.get_abac_attr("status") == "status_attr"
        assert fm.get_abac_attr("unknown") == "unknown"

    def test_get_field(self) -> None:
        fm = FieldMapping(mappings={"status": "status_attr"})
        assert fm.get_field("status_attr") == "status"
        assert fm.get_field("unknown") == "unknown"

    def test_cast_external_id(self) -> None:
        fm = FieldMapping(external_id_cast=int)
        assert fm.cast_external_id("42") == 42
        assert fm.cast_external_id(["1", "2"]) == [1, 2]


class TestAccessRule:
    def test_frozen(self) -> None:
        rule = AccessRule(principal_name="alice", action="read")
        with pytest.raises(AttributeError):
            rule.action = "write"  # type: ignore[misc]


class TestResourceTypeConfig:
    def test_defaults(self) -> None:
        config = ResourceTypeConfig(name="order", field_mapping=FieldMapping())
        assert config.is_public is False
        assert config.auto_register_resources is True
        assert config.actions == []


class TestExceptions:
    def test_permission_denied(self) -> None:
        e = PermissionDeniedError(
            resource_type="order", action="delete", resource_ids=["1"]
        )
        assert e.code == "PERMISSION_DENIED"
        assert e.resource_type == "order"
        assert e.action == "delete"
        assert isinstance(e, AccessControlError)

    def test_insufficient_role(self) -> None:
        e = InsufficientRoleError("admin")
        assert e.required_role == "admin"
        assert "admin" in str(e)

    def test_acl_error(self) -> None:
        e = ACLError("failed")
        assert e.code == "ACL_ERROR"

    def test_elevation_required(self) -> None:
        e = ElevationRequiredError("delete_tenant")
        assert e.code == "ELEVATION_REQUIRED"
        assert isinstance(e, PermissionDeniedError)


# ---------------------------------------------------------------------------
# AuthorizationFilter.from_specification
# ---------------------------------------------------------------------------


class TestAuthorizationFilterFromSpec:
    def test_from_specification(self) -> None:
        from cqrs_ddd_access_control.models import AuthorizationFilter

        class FakeSpec:
            pass

        spec = FakeSpec()
        af = AuthorizationFilter.from_specification(spec)  # type: ignore[arg-type]
        assert af.filter_specification is spec
        assert af.has_filter is True
        assert af.granted_all is False
        assert af.denied_all is False

    def test_grant_all(self) -> None:
        from cqrs_ddd_access_control.models import AuthorizationFilter

        af = AuthorizationFilter.grant_all()
        assert af.granted_all is True
        assert bool(af) is True

    def test_deny_all(self) -> None:
        from cqrs_ddd_access_control.models import AuthorizationFilter

        af = AuthorizationFilter.deny_all()
        assert af.denied_all is True
        assert bool(af) is False


# ---------------------------------------------------------------------------
# _resolve_bypass_roles
# ---------------------------------------------------------------------------


class TestResolveBypassRoles:
    def test_explicit_roles(self) -> None:
        from cqrs_ddd_access_control.models import _resolve_bypass_roles

        result = _resolve_bypass_roles(frozenset({"admin", "superadmin"}))
        assert result == frozenset({"admin", "superadmin"})

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from cqrs_ddd_access_control.models import _resolve_bypass_roles

        monkeypatch.setenv("AUTH_BYPASS_ROLES", "admin, superadmin")
        result = _resolve_bypass_roles()
        assert result == frozenset({"admin", "superadmin"})

    def test_no_env_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from cqrs_ddd_access_control.models import _resolve_bypass_roles

        monkeypatch.delenv("AUTH_BYPASS_ROLES", raising=False)
        result = _resolve_bypass_roles()
        assert result == frozenset()
