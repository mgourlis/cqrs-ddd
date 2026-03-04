"""Tests for decorators and DecoratorAuthorizationMiddleware."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from cqrs_ddd_access_control.decorators import (
    OwnershipRequirement,
    PermissionRequirement,
    RoleRequirement,
    authorization,
    get_authorization_config,
    get_ownership_requirement,
    get_permission_requirement,
    get_role_requirement,
    requires_owner,
    requires_permission,
    requires_role,
)
from cqrs_ddd_access_control.exceptions import (
    InsufficientRoleError,
    PermissionDeniedError,
)
from cqrs_ddd_access_control.middleware.decorator_middleware import (
    DecoratorAuthorizationMiddleware,
)
from cqrs_ddd_access_control.models import AuthorizationConfig
from cqrs_ddd_identity import Principal, set_principal

# ---------------------------------------------------------------------------
# Inline stubs
# ---------------------------------------------------------------------------


class _StubOwnershipResolver:
    def __init__(self, owners: dict[tuple[str, str], str] | None = None) -> None:
        self._owners = owners or {}

    async def get_owner(self, resource_type: str, resource_id: str) -> str | None:
        return self._owners.get((resource_type, resource_id))


# ---------------------------------------------------------------------------
# Decorator metadata tests
# ---------------------------------------------------------------------------


class TestRequiresPermission:
    def test_single_string(self) -> None:
        @requires_permission("order:read")
        class H:
            pass

        req = get_permission_requirement(H)
        assert req is not None
        assert req.permissions == ("order:read",)
        assert req.qualifier == "all"

    def test_list_default_qualifier(self) -> None:
        @requires_permission(["order:read", "order:write"])
        class H:
            pass

        req = get_permission_requirement(H)
        assert req is not None
        assert req.permissions == ("order:read", "order:write")
        assert req.qualifier == "all"

    def test_list_qualifier_any(self) -> None:
        @requires_permission(["order:read", "order:write"], "any")
        class H:
            pass

        req = get_permission_requirement(H)
        assert req is not None
        assert req.qualifier == "any"

    def test_list_qualifier_not(self) -> None:
        @requires_permission(["order:delete"], "not")
        class H:
            pass

        req = get_permission_requirement(H)
        assert req is not None
        assert req.qualifier == "not"

    def test_returns_none_for_undecorated(self) -> None:
        class H:
            pass

        assert get_permission_requirement(H) is None

    def test_frozen(self) -> None:
        req = PermissionRequirement(permissions=("a",), qualifier="all")
        with pytest.raises(AttributeError):
            req.permissions = ("b",)  # type: ignore[misc]


class TestRequiresRole:
    def test_single_string(self) -> None:
        @requires_role("admin")
        class H:
            pass

        req = get_role_requirement(H)
        assert req is not None
        assert req.roles == ("admin",)
        assert req.qualifier == "all"

    def test_list_qualifier_any(self) -> None:
        @requires_role(["admin", "editor"], "any")
        class H:
            pass

        req = get_role_requirement(H)
        assert req is not None
        assert req.roles == ("admin", "editor")
        assert req.qualifier == "any"

    def test_list_qualifier_not(self) -> None:
        @requires_role(["guest"], "not")
        class H:
            pass

        req = get_role_requirement(H)
        assert req is not None
        assert req.qualifier == "not"

    def test_returns_none_for_undecorated(self) -> None:
        assert get_role_requirement(int) is None


class TestRequiresOwner:
    def test_default_id_field(self) -> None:
        @requires_owner("order")
        class H:
            pass

        req = get_ownership_requirement(H)
        assert req is not None
        assert isinstance(req, OwnershipRequirement)
        assert req.resource_type == "order"
        assert req.id_field == "id"

    def test_custom_id_field(self) -> None:
        @requires_owner("invoice", id_field="invoice_id")
        class H:
            pass

        req = get_ownership_requirement(H)
        assert req is not None
        assert req.id_field == "invoice_id"


class TestAuthorizationDecorator:
    def test_sets_config(self) -> None:
        @authorization(
            resource_type="order",
            required_actions=["read", "write"],
            resource_id_attr="order_id",
        )
        class H:
            pass

        cfg = get_authorization_config(H)
        assert cfg is not None
        assert isinstance(cfg, AuthorizationConfig)
        assert cfg.resource_type == "order"
        assert cfg.required_actions == ["read", "write"]
        assert cfg.resource_id_attr == "order_id"

    def test_returns_none_for_undecorated(self) -> None:
        assert get_authorization_config(str) is None


class TestStackedDecorators:
    def test_permission_and_role(self) -> None:
        @requires_permission("order:read")
        @requires_role(["admin", "editor"], "any")
        class H:
            pass

        perm = get_permission_requirement(H)
        role = get_role_requirement(H)
        assert perm is not None
        assert perm.permissions == ("order:read",)
        assert role is not None
        assert role.qualifier == "any"


# ---------------------------------------------------------------------------
# DecoratorAuthorizationMiddleware tests
# ---------------------------------------------------------------------------


@dataclass
class FakeCommand:
    """Minimal command-like object for testing."""

    name: str = "test"
    order_id: str = "123"


class FakeHandlerRegistry:
    """Minimal stub that returns handler classes by message type."""

    def __init__(self) -> None:
        self._handlers: dict[type, type] = {}
        self._query_handlers: dict[type, type] = {}

    def register(self, message_cls: type, handler_cls: type) -> None:
        self._handlers[message_cls] = handler_cls

    def get_command_handler(self, message_type: type) -> type | None:
        return self._handlers.get(message_type)

    def get_query_handler(self, message_type: type) -> type | None:
        return self._query_handlers.get(message_type)


async def _noop_next(msg: Any) -> str:
    return "handler_result"


def _set_principal_ctx(principal: Principal | None):
    """Set principal in context and return the reset token."""
    from cqrs_ddd_identity.context import _principal_context

    if principal is not None:
        return set_principal(principal)
    return _principal_context.set(None)


def _reset_principal_ctx(token: Any) -> None:
    from cqrs_ddd_identity.context import _principal_context

    _principal_context.reset(token)


class TestDecoratorAuthMiddleware:
    """Tests for DecoratorAuthorizationMiddleware."""

    @pytest.mark.asyncio
    async def test_no_handler_passes_through(self) -> None:
        registry = FakeHandlerRegistry()
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        result = await mw(FakeCommand(), _noop_next)
        assert result == "handler_result"

    @pytest.mark.asyncio
    async def test_undecorated_handler_passes_through(self) -> None:
        class PlainHandler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, PlainHandler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(
            user_id="u1", username="u", roles=set(), permissions=set()
        )
        token = _set_principal_ctx(principal)
        try:
            result = await mw(FakeCommand(), _noop_next)
            assert result == "handler_result"
        finally:
            _reset_principal_ctx(token)

    # ── @requires_permission ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_permission_all_satisfied(self) -> None:
        @requires_permission(["order:read", "order:write"])
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(
            user_id="u1",
            username="u",
            roles=set(),
            permissions={"order:read", "order:write"},
        )
        token = _set_principal_ctx(principal)
        try:
            result = await mw(FakeCommand(), _noop_next)
            assert result == "handler_result"
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_permission_all_missing(self) -> None:
        @requires_permission(["order:read", "order:write"])
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(
            user_id="u1",
            username="u",
            roles=set(),
            permissions={"order:read"},
        )
        token = _set_principal_ctx(principal)
        try:
            with pytest.raises(PermissionDeniedError, match="Missing permissions"):
                await mw(FakeCommand(), _noop_next)
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_permission_any_satisfied(self) -> None:
        @requires_permission(["order:read", "order:write"], "any")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(
            user_id="u1",
            username="u",
            roles=set(),
            permissions={"order:read"},
        )
        token = _set_principal_ctx(principal)
        try:
            result = await mw(FakeCommand(), _noop_next)
            assert result == "handler_result"
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_permission_any_none_satisfied(self) -> None:
        @requires_permission(["order:delete", "order:admin"], "any")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(
            user_id="u1",
            username="u",
            roles=set(),
            permissions={"order:read"},
        )
        token = _set_principal_ctx(principal)
        try:
            with pytest.raises(PermissionDeniedError, match="Requires any of"):
                await mw(FakeCommand(), _noop_next)
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_permission_not_blocks(self) -> None:
        @requires_permission(["order:read"], "not")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(
            user_id="u1",
            username="u",
            roles=set(),
            permissions={"order:read"},
        )
        token = _set_principal_ctx(principal)
        try:
            with pytest.raises(PermissionDeniedError, match="Denied permissions"):
                await mw(FakeCommand(), _noop_next)
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_permission_not_allows(self) -> None:
        @requires_permission(["order:delete"], "not")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(
            user_id="u1",
            username="u",
            roles=set(),
            permissions={"order:read"},
        )
        token = _set_principal_ctx(principal)
        try:
            result = await mw(FakeCommand(), _noop_next)
            assert result == "handler_result"
        finally:
            _reset_principal_ctx(token)

    # ── @requires_role ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_role_all_satisfied(self) -> None:
        @requires_role(["admin", "editor"])
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(user_id="u1", username="u", roles={"admin", "editor"})
        token = _set_principal_ctx(principal)
        try:
            result = await mw(FakeCommand(), _noop_next)
            assert result == "handler_result"
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_role_all_missing(self) -> None:
        @requires_role(["admin", "editor"])
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(user_id="u1", username="u", roles={"editor"})
        token = _set_principal_ctx(principal)
        try:
            with pytest.raises(InsufficientRoleError, match="admin"):
                await mw(FakeCommand(), _noop_next)
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_role_any_satisfied(self) -> None:
        @requires_role(["admin", "moderator"], "any")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(user_id="u1", username="u", roles={"admin"})
        token = _set_principal_ctx(principal)
        try:
            result = await mw(FakeCommand(), _noop_next)
            assert result == "handler_result"
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_role_any_none_satisfied(self) -> None:
        @requires_role(["admin", "moderator"], "any")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(user_id="u1", username="u", roles={"viewer"})
        token = _set_principal_ctx(principal)
        try:
            with pytest.raises(InsufficientRoleError, match="Requires any role"):
                await mw(FakeCommand(), _noop_next)
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_role_not_blocks(self) -> None:
        @requires_role(["guest"], "not")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(user_id="u1", username="u", roles={"guest"})
        token = _set_principal_ctx(principal)
        try:
            with pytest.raises(InsufficientRoleError, match="Denied roles"):
                await mw(FakeCommand(), _noop_next)
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_role_not_allows(self) -> None:
        @requires_role(["guest"], "not")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        principal = Principal(user_id="u1", username="u", roles={"admin"})
        token = _set_principal_ctx(principal)
        try:
            result = await mw(FakeCommand(), _noop_next)
            assert result == "handler_result"
        finally:
            _reset_principal_ctx(token)

    # ── @requires_owner ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_owner_check_passes(self) -> None:
        @requires_owner("order", id_field="order_id")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        resolver = _StubOwnershipResolver(owners={("order", "123"): "u1"})
        mw = DecoratorAuthorizationMiddleware(
            handler_registry=registry,
            ownership_resolver=resolver,
        )

        principal = Principal(user_id="u1", username="u", roles=set())
        token = _set_principal_ctx(principal)
        try:
            result = await mw(FakeCommand(order_id="123"), _noop_next)
            assert result == "handler_result"
        finally:
            _reset_principal_ctx(token)

    @pytest.mark.asyncio
    async def test_owner_check_fails(self) -> None:
        @requires_owner("order", id_field="order_id")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        resolver = _StubOwnershipResolver(owners={("order", "123"): "other-user"})
        mw = DecoratorAuthorizationMiddleware(
            handler_registry=registry,
            ownership_resolver=resolver,
        )

        principal = Principal(user_id="u1", username="u", roles=set())
        token = _set_principal_ctx(principal)
        try:
            with pytest.raises(PermissionDeniedError, match="Ownership"):
                await mw(FakeCommand(order_id="123"), _noop_next)
        finally:
            _reset_principal_ctx(token)

    # ── bypass roles ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_bypass_roles_skip_checks(self) -> None:
        @requires_permission(["restricted:perm"])
        @requires_role(["restricted_role"])
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(
            handler_registry=registry,
            bypass_roles=frozenset({"superadmin"}),
        )

        principal = Principal(user_id="a1", username="admin", roles={"superadmin"})
        token = _set_principal_ctx(principal)
        try:
            result = await mw(FakeCommand(), _noop_next)
            assert result == "handler_result"
        finally:
            _reset_principal_ctx(token)

    # ── anonymous handling ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_anonymous_denied_for_permission(self) -> None:
        @requires_permission("order:read")
        class Handler:
            pass

        registry = FakeHandlerRegistry()
        registry.register(FakeCommand, Handler)
        mw = DecoratorAuthorizationMiddleware(handler_registry=registry)

        # No principal set → anonymous
        token = _set_principal_ctx(None)
        try:
            with pytest.raises(PermissionDeniedError, match="Anonymous"):
                await mw(FakeCommand(), _noop_next)
        finally:
            _reset_principal_ctx(token)
