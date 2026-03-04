"""Tests for authorization middleware stack."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from cqrs_ddd_access_control.exceptions import PermissionDeniedError
from cqrs_ddd_access_control.middleware.authorization import (
    AuthorizationMiddleware,
    _getattr_dotted,
    _setattr_dotted,
)
from cqrs_ddd_access_control.middleware.permitted_actions import (
    PermittedActionsMiddleware,
)
from cqrs_ddd_access_control.middleware.specification import SpecificationAuthMiddleware
from cqrs_ddd_access_control.models import (
    AuthorizationConditionsResult,
    AuthorizationConfig,
    AuthorizationFilter,
    CheckAccessBatchResult,
    FieldMapping,
    PermittedActionsConfig,
    ResourceTypeConfig,
    SpecificationAuthConfig,
)
from cqrs_ddd_identity import Principal, set_access_token, set_principal
from cqrs_ddd_identity.context import _access_token_context, _principal_context

# ---------------------------------------------------------------------------
# Auto-clean identity context
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_context():
    yield
    _principal_context.set(None)
    _access_token_context.set(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeMessage:
    resource_type: str = "order"
    resource_id: str | None = "o-1"
    query_options: Any | None = None


@dataclass
class _Entity:
    id: str
    permitted_actions: list[str] = field(default_factory=list)


@dataclass
class _Result:
    items: list[_Entity] = field(default_factory=list)


@dataclass
class _Nested:
    inner: _Inner | None = None


@dataclass
class _Inner:
    value: str = "original"


@dataclass
class _Specification:
    _filters: list[Any] = field(default_factory=list)

    def merge(self, other: Any) -> _Specification:
        return _Specification(_filters=[*self._filters, other])


@dataclass
class _QueryOptions:
    specification: _Specification | None = None

    def with_specification(self, spec: Any) -> _QueryOptions:
        return _QueryOptions(specification=spec)


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
        for c in self._configs.values():
            if c.entity_class is entity_cls:
                return c
        return None

    def list_types(self) -> list[str]:
        return list(self._configs)


# ---------------------------------------------------------------------------
# Tests — _getattr_dotted / _setattr_dotted
# ---------------------------------------------------------------------------


class TestDottedAttrHelpers:
    def test_getattr_dotted_simple(self) -> None:
        msg = _FakeMessage(resource_type="order")
        assert _getattr_dotted(msg, "resource_type") == "order"

    def test_getattr_dotted_nested(self) -> None:
        obj = _Nested(inner=_Inner(value="hello"))
        assert _getattr_dotted(obj, "inner.value") == "hello"

    def test_setattr_dotted_simple(self) -> None:
        obj = _FakeMessage()
        result = _setattr_dotted(obj, "resource_type", "doc")
        assert result.resource_type == "doc"

    def test_setattr_dotted_nested(self) -> None:
        obj = _Nested(inner=_Inner(value="original"))
        result = _setattr_dotted(obj, "inner.value", "updated")
        assert result.inner.value == "updated"

    def test_setattr_dotted_pydantic_model_copy(self) -> None:
        """Pydantic frozen models need model_copy path."""
        from pydantic import BaseModel, ConfigDict

        class Inner(BaseModel):
            model_config = ConfigDict(frozen=True)
            value: str = "original"

        class Outer(BaseModel):
            model_config = ConfigDict(frozen=True)
            inner: Inner = Inner()

        obj = Outer()
        result = _setattr_dotted(obj, "inner.value", "updated")
        assert result.inner.value == "updated"


# ---------------------------------------------------------------------------
# Tests — AuthorizationMiddleware
# ---------------------------------------------------------------------------


class TestAuthorizationMiddleware:
    @pytest.mark.asyncio
    async def test_bypass_role_skips_check(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
        )
        mw = AuthorizationMiddleware(
            stub_auth_port,
            config,
            bypass_roles=frozenset({"editor"}),
        )

        called = False

        async def handler(msg: Any) -> str:
            nonlocal called
            called = True
            return "ok"

        result = await mw(_FakeMessage(), handler)
        assert result == "ok"
        assert called

    @pytest.mark.asyncio
    async def test_deny_anonymous(
        self,
        stub_auth_port: Any,
    ) -> None:
        _principal_context.set(None)
        set_access_token(None)

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            deny_anonymous=True,
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        with pytest.raises(PermissionDeniedError) as exc_info:
            await mw(_FakeMessage(), handler)
        assert exc_info.value.reason == "Anonymous access denied"

    @pytest.mark.asyncio
    async def test_pre_check_allows(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        # Allow o-1 for read
        stub_auth_port.allowed_ids[("order", "read")] = ["o-1"]

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            resource_id_attr="resource_id",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(resource_id="o-1"), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_pre_check_denies(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        # No access
        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            resource_id_attr="resource_id",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        with pytest.raises(PermissionDeniedError) as exc_info:
            await mw(_FakeMessage(resource_id="o-1"), handler)
        assert "pre-check" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_pre_check_fail_silently(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            resource_id_attr="resource_id",
            fail_silently=True,
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(resource_id="o-1"), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_post_filter_entities(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.allowed_ids[("order", "read")] = ["o-1"]

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            result_entities_attr="items",
            entity_id_attr="id",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        result_obj = _Result(
            items=[_Entity(id="o-1"), _Entity(id="o-2")],
        )

        async def handler(msg: Any) -> _Result:
            return result_obj

        result = await mw(_FakeMessage(), handler)
        assert len(result.items) == 1
        assert result.items[0].id == "o-1"

    @pytest.mark.asyncio
    async def test_post_filter_no_entities_attr(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            result_entities_attr="nonexistent",
            entity_id_attr="id",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_resource_type_from_attr(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.allowed_ids[("order", "read")] = ["o-1"]

        config = AuthorizationConfig(
            resource_type_attr="resource_type",
            required_actions=["read"],
            resource_id_attr="resource_id",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(
            _FakeMessage(resource_type="order", resource_id="o-1"), handler
        )
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_resource_ids_skips_pre_check(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            # No resource_id_attr → no pre-check
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_principal_no_bypass(
        self,
        stub_auth_port: Any,
    ) -> None:
        _principal_context.set(None)
        set_access_token("tok")

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
        )
        mw = AuthorizationMiddleware(
            stub_auth_port,
            config,
            bypass_roles=frozenset({"admin"}),
        )

        async def handler(msg: Any) -> str:
            return "ok"

        # No principal → bypass check should be skipped
        result = await mw(_FakeMessage(), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_auth_context_provider(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.allowed_ids[("order", "read")] = ["o-1"]

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            resource_id_attr="resource_id",
            auth_context_provider=lambda msg: {"tenant": "t-1"},
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(resource_id="o-1"), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_resource_id_attr_returns_none(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            resource_id_attr="resource_id",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        # resource_id=None on message → no resource IDs extracted → skip pre-check
        result = await mw(_FakeMessage(resource_id=None), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_resource_id_list(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.allowed_ids[("order", "read")] = ["1", "2"]

        @dataclass
        class _ListMsg:
            resource_type: str = "order"
            ids: list[str] = field(default_factory=lambda: ["1", "2"])

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            resource_id_attr="ids",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_ListMsg(), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_post_filter_non_list_entities(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read"],
            result_entities_attr="items",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        @dataclass
        class _PlainResult:
            items: str = "not-a-list"

        async def handler(msg: Any) -> _PlainResult:
            return _PlainResult()

        result = await mw(_FakeMessage(), handler)
        assert result.items == "not-a-list"

    @pytest.mark.asyncio
    async def test_action_quantifier_any(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        # Only "read" allowed, not "write"
        stub_auth_port.allowed_ids[("order", "read")] = ["o-1"]

        config = AuthorizationConfig(
            resource_type="order",
            required_actions=["read", "write"],
            resource_id_attr="resource_id",
            action_quantifier="any",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        # With "any", having at least one matching action is enough
        result = await mw(_FakeMessage(resource_id="o-1"), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_resource_type_resolved(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = AuthorizationConfig(
            # Neither resource_type nor resource_type_attr set
            required_actions=["read"],
            resource_id_attr="resource_id",
        )
        mw = AuthorizationMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "ok"

        # No resource type → skip pre-check
        result = await mw(_FakeMessage(resource_id="o-1"), handler)
        assert result == "ok"


# ---------------------------------------------------------------------------
# Tests — SpecificationAuthMiddleware
# ---------------------------------------------------------------------------


class TestSpecificationAuthMiddleware:
    @pytest.mark.asyncio
    async def test_bypass_role(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = SpecificationAuthConfig(resource_type="order", action="read")
        registry = _StubRegistry()
        mw = SpecificationAuthMiddleware(
            stub_auth_port,
            config,
            registry,
            bypass_roles=frozenset({"editor"}),
        )

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_denied_all_raises(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        # Default stub returns denied_all
        config = SpecificationAuthConfig(resource_type="order", action="read")
        registry = _StubRegistry()
        mw = SpecificationAuthMiddleware(stub_auth_port, config, registry)

        async def handler(msg: Any) -> str:
            return "ok"

        with pytest.raises(PermissionDeniedError) as exc_info:
            await mw(_FakeMessage(), handler)
        assert "denied" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_granted_all_passes(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.conditions[("order", "read")] = AuthorizationConditionsResult(
            filter_type="granted_all",
        )

        config = SpecificationAuthConfig(resource_type="order", action="read")
        registry = _StubRegistry()
        mw = SpecificationAuthMiddleware(stub_auth_port, config, registry)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_field_mapping_resolved_from_registry(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.conditions[("order", "read")] = AuthorizationConditionsResult(
            filter_type="granted_all",
        )

        registry = _StubRegistry(
            {
                "order": ResourceTypeConfig(
                    name="order",
                    field_mapping=FieldMapping(mappings={"status": "order_status"}),
                ),
            }
        )
        config = SpecificationAuthConfig(resource_type="order", action="read")
        mw = SpecificationAuthMiddleware(stub_auth_port, config, registry)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_auth_context_provider(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.conditions[("order", "read")] = AuthorizationConditionsResult(
            filter_type="granted_all",
        )

        config = SpecificationAuthConfig(
            resource_type="order",
            action="read",
            auth_context_provider=lambda msg: {"tenant": "t-1"},
        )
        registry = _StubRegistry()
        mw = SpecificationAuthMiddleware(stub_auth_port, config, registry)

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_has_filter_merges_with_existing_spec(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        """Cover lines 83-93: has_filter path with existing specification."""
        set_principal(principal)
        set_access_token("tok")

        # Need to override get_authorization_filter to return a filter with has_filter=True
        existing_spec = _Specification(_filters=["existing"])
        auth_spec = _Specification(_filters=["auth"])

        async def custom_get_filter(*a: Any, **kw: Any) -> AuthorizationFilter:
            return AuthorizationFilter(filter_specification=auth_spec)  # type: ignore[arg-type]

        stub_auth_port.get_authorization_filter = custom_get_filter

        from pydantic import BaseModel

        class FakeQueryOptions(BaseModel):
            specification: _Specification | None = None

            def with_specification(self, spec: Any) -> FakeQueryOptions:
                return FakeQueryOptions(specification=spec)

        class FakeMessage(BaseModel):
            query_options: FakeQueryOptions = FakeQueryOptions(
                specification=existing_spec,
            )

        config = SpecificationAuthConfig(
            resource_type="order",
            action="read",
        )
        registry = _StubRegistry()
        mw = SpecificationAuthMiddleware(stub_auth_port, config, registry)

        captured = {}

        async def handler(msg: Any) -> str:
            captured["msg"] = msg
            return "ok"

        result = await mw(FakeMessage(), handler)
        assert result == "ok"
        # Merged specification should have both filters
        merged = captured["msg"].query_options.specification
        assert "existing" in str(merged._filters)
        assert "auth" in str(merged._filters)

    @pytest.mark.asyncio
    async def test_has_filter_no_existing_spec(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        """Cover the else branch: no existing specification."""
        set_principal(principal)
        set_access_token("tok")

        auth_spec = _Specification(_filters=["auth"])

        async def custom_get_filter(*a: Any, **kw: Any) -> AuthorizationFilter:
            return AuthorizationFilter(filter_specification=auth_spec)  # type: ignore[arg-type]

        stub_auth_port.get_authorization_filter = custom_get_filter

        from pydantic import BaseModel

        class FakeQueryOptions(BaseModel):
            specification: _Specification | None = None

            def with_specification(self, spec: Any) -> FakeQueryOptions:
                return FakeQueryOptions(specification=spec)

        class FakeMessage(BaseModel):
            query_options: FakeQueryOptions = FakeQueryOptions(specification=None)

        config = SpecificationAuthConfig(
            resource_type="order",
            action="read",
        )
        registry = _StubRegistry()
        mw = SpecificationAuthMiddleware(stub_auth_port, config, registry)

        captured = {}

        async def handler(msg: Any) -> str:
            captured["msg"] = msg
            return "ok"

        result = await mw(FakeMessage(), handler)
        assert result == "ok"
        assert captured["msg"].query_options.specification is auth_spec

    @pytest.mark.asyncio
    async def test_has_filter_no_query_options(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        """Cover the case where query_options is None."""
        set_principal(principal)
        set_access_token("tok")

        auth_spec = _Specification(_filters=["auth"])

        async def custom_get_filter(*a: Any, **kw: Any) -> AuthorizationFilter:
            return AuthorizationFilter(filter_specification=auth_spec)  # type: ignore[arg-type]

        stub_auth_port.get_authorization_filter = custom_get_filter

        config = SpecificationAuthConfig(
            resource_type="order",
            action="read",
        )
        registry = _StubRegistry()
        mw = SpecificationAuthMiddleware(stub_auth_port, config, registry)

        async def handler(msg: Any) -> str:
            return "ok"

        # _FakeMessage has query_options=None
        result = await mw(_FakeMessage(), handler)
        assert result == "ok"


# ---------------------------------------------------------------------------
# Tests — PermittedActionsMiddleware
# ---------------------------------------------------------------------------


class TestPermittedActionsMiddleware:
    @pytest.mark.asyncio
    async def test_enriches_entities(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.permitted_actions["order"] = {
            "o-1": ["read", "write"],
            "o-2": ["read"],
        }

        config = PermittedActionsConfig(
            resource_type="order",
            result_entities_attr="items",
            entity_id_attr="id",
        )
        mw = PermittedActionsMiddleware(stub_auth_port, config)

        result_obj = _Result(
            items=[_Entity(id="o-1"), _Entity(id="o-2")],
        )

        async def handler(msg: Any) -> _Result:
            return result_obj

        result = await mw(_FakeMessage(), handler)
        assert set(result.items[0].permitted_actions) == {"read", "write"}
        assert result.items[1].permitted_actions == ["read"]

    @pytest.mark.asyncio
    async def test_bypass_role(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = PermittedActionsConfig(resource_type="order")
        mw = PermittedActionsMiddleware(
            stub_auth_port,
            config,
            bypass_roles=frozenset({"editor"}),
        )

        async def handler(msg: Any) -> str:
            return "ok"

        result = await mw(_FakeMessage(), handler)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_entities_in_result(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = PermittedActionsConfig(
            resource_type="order",
            result_entities_attr="items",
        )
        mw = PermittedActionsMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> str:
            return "scalar_result"

        result = await mw(_FakeMessage(), handler)
        assert result == "scalar_result"

    @pytest.mark.asyncio
    async def test_empty_entity_list(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = PermittedActionsConfig(
            resource_type="order",
            result_entities_attr="items",
        )
        mw = PermittedActionsMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> _Result:
            return _Result(items=[])

        result = await mw(_FakeMessage(), handler)
        assert result.items == []

    @pytest.mark.asyncio
    async def test_include_type_level_permissions(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.permitted_actions["order"] = {
            "o-1": ["read"],
        }
        stub_auth_port.type_level_perms["order"] = ["list"]

        config = PermittedActionsConfig(
            resource_type="order",
            result_entities_attr="items",
            entity_id_attr="id",
            include_type_level=True,
        )
        mw = PermittedActionsMiddleware(stub_auth_port, config)

        result_obj = _Result(items=[_Entity(id="o-1")])

        async def handler(msg: Any) -> _Result:
            return result_obj

        result = await mw(_FakeMessage(), handler)
        # Should merge resource-level + type-level permissions
        assert "read" in result.items[0].permitted_actions
        assert "list" in result.items[0].permitted_actions

    @pytest.mark.asyncio
    async def test_auth_context_provider(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        stub_auth_port.permitted_actions["order"] = {"o-1": ["read"]}

        config = PermittedActionsConfig(
            resource_type="order",
            result_entities_attr="items",
            entity_id_attr="id",
            auth_context_provider=lambda msg: {"tenant": "t-1"},
        )
        mw = PermittedActionsMiddleware(stub_auth_port, config)

        async def handler(msg: Any) -> _Result:
            return _Result(items=[_Entity(id="o-1")])

        result = await mw(_FakeMessage(), handler)
        assert result.items[0].permitted_actions == ["read"]

    @pytest.mark.asyncio
    async def test_frozen_entity_model_copy(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        from pydantic import BaseModel, ConfigDict

        class FrozenEntity(BaseModel):
            model_config = ConfigDict(frozen=True)
            id: str
            permitted_actions: list[str] = []

        stub_auth_port.permitted_actions["order"] = {"e-1": ["read"]}

        config = PermittedActionsConfig(
            resource_type="order",
            result_entities_attr="items",
            entity_id_attr="id",
        )
        mw = PermittedActionsMiddleware(stub_auth_port, config)

        @dataclass
        class FrozenResult:
            items: list[FrozenEntity] = field(default_factory=list)

        async def handler(msg: Any) -> FrozenResult:
            return FrozenResult(items=[FrozenEntity(id="e-1")])

        result = await mw(_FakeMessage(), handler)
        assert "read" in result.items[0].permitted_actions

    @pytest.mark.asyncio
    async def test_entities_without_id_attr(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_principal(principal)
        set_access_token("tok")

        config = PermittedActionsConfig(
            resource_type="order",
            result_entities_attr="items",
            entity_id_attr="id",
        )
        mw = PermittedActionsMiddleware(stub_auth_port, config)

        @dataclass
        class _NoIdEntity:
            name: str = "foo"

        @dataclass
        class _NoIdResult:
            items: list[_NoIdEntity] = field(default_factory=list)

        async def handler(msg: Any) -> _NoIdResult:
            return _NoIdResult(items=[_NoIdEntity()])

        result = await mw(_FakeMessage(), handler)
        # Should return unmodified since no entity_ids extracted
        assert len(result.items) == 1
