"""Tests for FastAPI dependencies (optional; requires identity[fastapi])."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import HTTPException

from cqrs_ddd_identity import Principal
from cqrs_ddd_identity.context import clear_principal, set_principal
from cqrs_ddd_identity.contrib.fastapi.dependencies import (
    get_principal,
    get_principal_optional,
    require_authenticated,
    require_permission,
    require_role,
)


@pytest.fixture(autouse=True)
def clear_context() -> None:
    clear_principal()
    yield
    clear_principal()


@pytest.fixture
def admin_principal() -> Principal:
    return Principal(
        user_id="u1",
        username="admin",
        roles=frozenset(["admin"]),
        permissions=frozenset(["read", "write"]),
    )


@pytest.fixture
def user_principal() -> Principal:
    return Principal(
        user_id="u2",
        username="user",
        roles=frozenset(["user"]),
        permissions=frozenset(["read"]),
    )


class TestGetPrincipal:
    def test_raises_401_when_no_principal(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            get_principal()
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in str(exc_info.value.detail)
        assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"

    def test_returns_principal_when_set(self, admin_principal: Principal) -> None:
        set_principal(admin_principal)
        assert get_principal() == admin_principal


class TestGetPrincipalOptional:
    def test_returns_none_when_not_set(self) -> None:
        assert get_principal_optional() is None

    def test_returns_principal_when_set(self, admin_principal: Principal) -> None:
        set_principal(admin_principal)
        assert get_principal_optional() == admin_principal


class TestRequireRole:
    def test_success_when_has_role(self, admin_principal: Principal) -> None:
        set_principal(admin_principal)
        dep = require_role("admin")
        result = dep(get_principal())
        assert result == admin_principal

    def test_raises_403_when_missing_role(self, user_principal: Principal) -> None:
        set_principal(user_principal)
        dep = require_role("admin")
        with pytest.raises(HTTPException) as exc_info:
            dep(get_principal())
        assert exc_info.value.status_code == 403
        assert "admin" in str(exc_info.value.detail)


class TestRequirePermission:
    def test_success_when_has_permission(self, admin_principal: Principal) -> None:
        set_principal(admin_principal)
        dep = require_permission("write")
        result = dep(get_principal())
        assert result == admin_principal

    def test_raises_403_when_missing_permission(
        self, user_principal: Principal
    ) -> None:
        set_principal(user_principal)
        dep = require_permission("write")
        with pytest.raises(HTTPException) as exc_info:
            dep(get_principal())
        assert exc_info.value.status_code == 403


class TestRequireAuthenticated:
    def test_returns_principal_when_set(self, admin_principal: Principal) -> None:
        set_principal(admin_principal)
        assert require_authenticated() == admin_principal

    def test_raises_401_when_not_set(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            require_authenticated()
        assert exc_info.value.status_code == 401
