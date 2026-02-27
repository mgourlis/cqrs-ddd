"""Tests for Principal value object."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cqrs_ddd_identity import Principal


class TestPrincipalCreation:
    """Tests for Principal creation."""

    def test_create_principal(self) -> None:
        """Test creating a principal with all fields."""
        principal = Principal(
            user_id="user-123",
            username="john@example.com",
            roles=frozenset(["admin", "user"]),
            permissions=frozenset(["read:orders", "write:orders"]),
            claims={"email": "john@example.com"},
            tenant_id="acme",
            mfa_verified=True,
            auth_method="oauth2",
        )

        assert principal.user_id == "user-123"
        assert principal.username == "john@example.com"
        assert principal.roles == frozenset(["admin", "user"])
        assert principal.permissions == frozenset(["read:orders", "write:orders"])
        assert principal.claims == {"email": "john@example.com"}
        assert principal.tenant_id == "acme"
        assert principal.mfa_verified is True
        assert principal.auth_method == "oauth2"

    def test_create_anonymous(self) -> None:
        """Test creating anonymous principal."""
        principal = Principal.anonymous()

        assert principal.user_id == "anonymous"
        assert principal.username == "anonymous"
        assert principal.is_anonymous is True
        assert principal.is_authenticated is False

    def test_create_system(self) -> None:
        """Test creating system principal."""
        principal = Principal.system()

        assert principal.user_id == "system"
        assert principal.username == "system"
        assert principal.is_system is True
        assert principal.roles == frozenset(["*"])
        assert principal.permissions == frozenset(["*"])

    def test_default_values(self) -> None:
        """Test default values."""
        principal = Principal(user_id="user-1", username="user1")

        assert principal.roles == frozenset()
        assert principal.permissions == frozenset()
        assert principal.claims == {}
        assert principal.tenant_id is None
        assert principal.mfa_verified is False
        assert principal.auth_method == "jwt"
        assert principal.session_id is None
        assert principal.expires_at is None


class TestPrincipalFromJwtClaims:
    """Tests for Principal.from_jwt_claims factory method."""

    def test_from_basic_claims(self) -> None:
        """Test creating from basic JWT claims."""
        claims = {
            "sub": "user-123",
            "email": "user@example.com",
            "name": "Test User",
        }

        principal = Principal.from_jwt_claims(claims)

        assert principal.user_id == "user-123"
        assert principal.username == "user@example.com"
        assert principal.auth_method == "jwt"

    def test_from_keycloak_claims(self) -> None:
        """Test creating from Keycloak-style claims."""
        claims = {
            "sub": "keycloak-user-123",
            "preferred_username": "keycloakuser",
            "realm_access": {"roles": ["admin", "user"]},
            "tenant_id": "acme-corp",
        }

        principal = Principal.from_jwt_claims(claims)

        assert principal.user_id == "keycloak-user-123"
        assert principal.username == "keycloakuser"
        assert principal.has_role("admin")
        assert principal.has_role("user")
        assert principal.tenant_id == "acme-corp"

    def test_from_claims_with_expiration(self) -> None:
        """Test creating from claims with exp claim."""
        future_exp = (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
        claims = {"sub": "user-123", "exp": future_exp}

        principal = Principal.from_jwt_claims(claims)

        assert principal.expires_at is not None
        assert principal.is_expired is False

    def test_from_claims_with_groups(self) -> None:
        """Test creating from claims with groups as roles."""
        claims = {
            "sub": "user-123",
            "groups": ["developers", "admins"],
        }

        principal = Principal.from_jwt_claims(claims)

        assert principal.has_role("developers")
        assert principal.has_role("admins")


class TestPrincipalFromOAuthIntrospection:
    """Tests for Principal.from_oauth_introspection factory method."""

    def test_from_introspection_response(self) -> None:
        """Test creating from OAuth introspection response."""
        data = {
            "sub": "oauth-user-123",
            "username": "oauthuser",
            "active": True,
            "roles": ["user"],
            "permissions": ["read:profile"],
        }

        principal = Principal.from_oauth_introspection(data)

        assert principal.user_id == "oauth-user-123"
        assert principal.username == "oauthuser"
        assert principal.auth_method == "oauth2"
        assert principal.has_role("user")
        assert principal.has_permission("read:profile")


class TestPrincipalExpiration:
    """Tests for Principal expiration checks."""

    def test_not_expired_when_no_expiration(self) -> None:
        """Test principal without expiration is not expired."""
        principal = Principal(user_id="user-1", username="user1")

        assert principal.is_expired is False

    def test_not_expired_when_future_expiration(self) -> None:
        """Test principal with future expiration is not expired."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        assert principal.is_expired is False

    def test_expired_when_past_expiration(self) -> None:
        """Test principal with past expiration is expired."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        assert principal.is_expired is True

    def test_handles_naive_datetime_as_utc(self) -> None:
        """Test that naive datetime is treated as UTC."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            expires_at=datetime.now() + timedelta(hours=1),  # Naive
        )

        assert principal.is_expired is False


class TestPrincipalRoleChecks:
    """Tests for Principal role checking methods."""

    def test_has_role(self) -> None:
        """Test has_role method."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            roles=frozenset(["admin", "user"]),
        )

        assert principal.has_role("admin") is True
        assert principal.has_role("user") is True
        assert principal.has_role("superadmin") is False

    def test_wildcard_role(self) -> None:
        """Test wildcard role matches all."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            roles=frozenset(["*"]),
        )

        assert principal.has_role("any-role") is True
        assert principal.has_role("admin") is True

    def test_has_any_role(self) -> None:
        """Test has_any_role method."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            roles=frozenset(["user"]),
        )

        assert principal.has_any_role("admin", "user") is True
        assert principal.has_any_role("admin", "superadmin") is False

    def test_has_all_roles(self) -> None:
        """Test has_all_roles method."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            roles=frozenset(["admin", "user"]),
        )

        assert principal.has_all_roles("admin", "user") is True
        assert principal.has_all_roles("admin", "superadmin") is False


class TestPrincipalPermissionChecks:
    """Tests for Principal permission checking methods."""

    def test_has_permission(self) -> None:
        """Test has_permission method."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            permissions=frozenset(["read:orders", "write:orders"]),
        )

        assert principal.has_permission("read:orders") is True
        assert principal.has_permission("delete:orders") is False

    def test_wildcard_permission(self) -> None:
        """Test wildcard permission matches all."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            permissions=frozenset(["*"]),
        )

        assert principal.has_permission("any:permission") is True

    def test_has_any_permission(self) -> None:
        """Test has_any_permission method."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            permissions=frozenset(["read:orders"]),
        )

        assert principal.has_any_permission("read:orders", "write:orders") is True
        assert principal.has_any_permission("delete:orders", "update:orders") is False

    def test_has_all_permissions(self) -> None:
        """Test has_all_permissions method."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            permissions=frozenset(["read:orders", "write:orders"]),
        )

        assert principal.has_all_permissions("read:orders", "write:orders") is True
        assert principal.has_all_permissions("read:orders", "delete:orders") is False


class TestPrincipalImmutability:
    """Tests for Principal immutability."""

    def test_principal_is_frozen(self) -> None:
        """Test that principal cannot be modified."""
        principal = Principal(user_id="user-1", username="user1")

        with pytest.raises(Exception):  # Pydantic raises ValidationError
            principal.user_id = "modified"  # type: ignore[misc]

    def test_with_mfa_verified_returns_new_instance(self) -> None:
        """Test with_mfa_verified returns new instance."""
        principal = Principal(user_id="user-1", username="user1", mfa_verified=False)
        new_principal = principal.with_mfa_verified()

        assert principal.mfa_verified is False
        assert new_principal.mfa_verified is True
        assert principal is not new_principal

    def test_with_roles_returns_new_instance(self) -> None:
        """Test with_roles returns new instance."""
        principal = Principal(
            user_id="user-1", username="user1", roles=frozenset(["user"])
        )
        new_principal = principal.with_roles("admin")

        assert principal.roles == frozenset(["user"])
        assert new_principal.roles == frozenset(["user", "admin"])

    def test_with_permissions_returns_new_instance(self) -> None:
        """Test with_permissions returns new instance."""
        principal = Principal(
            user_id="user-1",
            username="user1",
            permissions=frozenset(["read:orders"]),
        )
        new_principal = principal.with_permissions("write:orders")

        assert principal.permissions == frozenset(["read:orders"])
        assert new_principal.permissions == frozenset(["read:orders", "write:orders"])


class TestPrincipalEquality:
    """Tests for Principal equality."""

    def test_equal_principals(self) -> None:
        """Test that identical principals are equal."""
        p1 = Principal(user_id="user-1", username="user1", roles=frozenset(["admin"]))
        p2 = Principal(user_id="user-1", username="user1", roles=frozenset(["admin"]))

        assert p1 == p2

    def test_different_principals(self) -> None:
        """Test that different principals are not equal."""
        p1 = Principal(user_id="user-1", username="user1")
        p2 = Principal(user_id="user-2", username="user2")

        assert p1 != p2

    def test_hash_consistency(self) -> None:
        """Test that equal principals have same hash."""
        p1 = Principal(user_id="user-1", username="user1", roles=frozenset(["admin"]))
        p2 = Principal(user_id="user-1", username="user1", roles=frozenset(["admin"]))

        assert hash(p1) == hash(p2)

    def test_can_be_used_in_set(self) -> None:
        """Test that principals can be used in sets."""
        p1 = Principal(user_id="user-1", username="user1")
        p2 = Principal(user_id="user-1", username="user1")
        p3 = Principal(user_id="user-2", username="user2")

        principal_set = {p1, p2, p3}

        assert len(principal_set) == 2
