"""Tests for Principal context management."""

from __future__ import annotations

import pytest

from cqrs_ddd_identity import IdentityPermissionError, Principal
from cqrs_ddd_identity.context import (
    clear_principal,
    get_current_principal,
    get_current_principal_or_none,
    get_tenant_id,
    get_user_id,
    get_user_id_or_none,
    is_authenticated,
    require_authenticated,
    require_permission,
    require_role,
    reset_principal,
    set_principal,
)


class TestGetSetPrincipal:
    """Tests for setting and getting principal from context."""

    def test_set_and_get_principal(self, principal: Principal) -> None:
        """Test setting and getting principal."""
        set_principal(principal)
        result = get_current_principal()

        assert result == principal

    def test_get_principal_or_none_when_set(self, principal: Principal) -> None:
        """Test getting principal when set."""
        set_principal(principal)
        result = get_current_principal_or_none()

        assert result == principal

    def test_get_principal_or_none_when_not_set(self) -> None:
        """Test getting principal when not set returns None."""
        clear_principal()
        result = get_current_principal_or_none()

        assert result is None

    def test_get_principal_raises_when_not_set(self) -> None:
        """Test that get_current_principal raises when not set."""
        clear_principal()

        with pytest.raises(LookupError, match="No principal in context"):
            get_current_principal()

    def test_clear_principal(self, principal: Principal) -> None:
        """Test clearing principal from context."""
        set_principal(principal)
        clear_principal()

        assert get_current_principal_or_none() is None

    def test_reset_principal(self, principal: Principal) -> None:
        """Test resetting principal to previous value."""
        original = Principal(user_id="original", username="original")
        set_principal(original)

        token = set_principal(principal)
        assert get_current_principal() == principal

        reset_principal(token)
        assert get_current_principal() == original


class TestConvenienceFunctions:
    """Tests for convenience context functions."""

    def test_get_user_id(self, principal: Principal) -> None:
        """Test getting user ID."""
        set_principal(principal)
        user_id = get_user_id()

        assert user_id == principal.user_id

    def test_get_user_id_raises_when_not_set(self) -> None:
        """Test that get_user_id raises when not set."""
        clear_principal()

        with pytest.raises(LookupError):
            get_user_id()

    def test_get_user_id_or_none(self, principal: Principal) -> None:
        """Test getting user ID or None."""
        set_principal(principal)
        assert get_user_id_or_none() == principal.user_id

        clear_principal()
        assert get_user_id_or_none() is None

    def test_get_tenant_id(self, principal: Principal) -> None:
        """Test getting tenant ID."""
        set_principal(principal)
        tenant_id = get_tenant_id()

        assert tenant_id == principal.tenant_id

    def test_get_tenant_id_when_none(self) -> None:
        """Test getting tenant ID when not set."""
        clear_principal()
        tenant_id = get_tenant_id()

        assert tenant_id is None

    def test_is_authenticated_when_authenticated(self, principal: Principal) -> None:
        """Test is_authenticated returns True for authenticated user."""
        set_principal(principal)
        assert is_authenticated() is True

    def test_is_authenticated_when_anonymous(self) -> None:
        """Test is_authenticated returns False for anonymous user."""
        set_principal(Principal.anonymous())
        assert is_authenticated() is False

    def test_is_authenticated_when_not_set(self) -> None:
        """Test is_authenticated returns False when not set."""
        clear_principal()
        assert is_authenticated() is False


class TestRequireFunctions:
    """Tests for require_* functions."""

    def test_require_role_success(self, principal: Principal) -> None:
        """Test require_role succeeds when role is present."""
        set_principal(principal)

        # Should not raise
        require_role("admin")

    def test_require_role_failure(self, principal: Principal) -> None:
        """Test require_role fails when role is missing."""
        set_principal(principal)

        with pytest.raises(IdentityPermissionError, match="Role 'superadmin' required"):
            require_role("superadmin")

    def test_require_role_raises_when_not_set(self) -> None:
        """Test require_role raises when principal not set."""
        clear_principal()

        with pytest.raises(LookupError):
            require_role("admin")

    def test_require_permission_success(self, principal: Principal) -> None:
        """Test require_permission succeeds when permission is present."""
        set_principal(principal)

        # Should not raise
        require_permission("read:orders")

    def test_require_permission_failure(self, principal: Principal) -> None:
        """Test require_permission fails when permission is missing."""
        set_principal(principal)

        with pytest.raises(
            IdentityPermissionError, match="Permission 'delete:orders' required"
        ):
            require_permission("delete:orders")

    def test_require_authenticated_success(self, principal: Principal) -> None:
        """Test require_authenticated succeeds for authenticated user."""
        set_principal(principal)

        # Should not raise
        require_authenticated()

    def test_require_authenticated_failure_anonymous(self) -> None:
        """Test require_authenticated fails for anonymous user."""
        set_principal(Principal.anonymous())

        with pytest.raises(LookupError, match="Authentication required"):
            require_authenticated()

    def test_require_authenticated_failure_not_set(self) -> None:
        """Test require_authenticated fails when not set."""
        clear_principal()

        with pytest.raises(LookupError):
            require_authenticated()


class TestWildcardPrincipal:
    """Tests for wildcard role/permission matching."""

    def test_require_role_with_wildcard(self) -> None:
        """Test that wildcard role satisfies any role requirement."""
        principal = Principal(
            user_id="system",
            username="system",
            roles=frozenset(["*"]),
        )
        set_principal(principal)

        # Should not raise for any role
        require_role("any-role")
        require_role("admin")
        require_role("superadmin")

    def test_require_permission_with_wildcard(self) -> None:
        """Test that wildcard permission satisfies any permission requirement."""
        principal = Principal(
            user_id="system",
            username="system",
            permissions=frozenset(["*"]),
        )
        set_principal(principal)

        # Should not raise for any permission
        require_permission("any:permission")
        require_permission("delete:all")
