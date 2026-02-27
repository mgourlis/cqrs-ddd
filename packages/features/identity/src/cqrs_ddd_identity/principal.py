"""Principal Value Object representing an authenticated identity.

Principal is an immutable value object that encapsulates all identity
information about an authenticated user or service.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from cqrs_ddd_core.domain import ValueObject


class Principal(ValueObject):
    """Immutable Principal value object representing an authenticated identity.

    A Principal contains all identity information needed for authorization
    decisions and audit logging. It is immutable (frozen=True via ValueObject).

    Attributes:
        user_id: Unique identifier for the user (subject claim).
        username: Human-readable username or email.
        roles: Set of role names the user has. Use frozenset for immutability.
        permissions: Set of permission strings the user has.
        claims: Raw claims from the identity provider (JWT, OAuth, etc.).
        tenant_id: Optional tenant identifier for multi-tenant systems.
        mfa_verified: Whether MFA has been completed for this session.
        auth_method: How the user authenticated (jwt, oauth2, ldap, apikey, db).
        session_id: Optional session identifier.
        expires_at: Token/session expiration time (timezone-aware UTC).

    Example:
        ```python
        principal = Principal(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            username="john.doe@example.com",
            roles=frozenset(["admin", "user"]),
            permissions=frozenset(["read:orders", "write:orders"]),
            claims={"email": "john.doe@example.com", "name": "John Doe"},
            tenant_id="acme-corp",
            mfa_verified=True,
            auth_method="oauth2",
        )

        if principal.has_permission("write:orders"):
            # Allow order modification
            pass
        ```
    """

    user_id: str
    username: str
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    claims: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None
    mfa_verified: bool = False
    auth_method: Literal["jwt", "oauth2", "ldap", "apikey", "db"] = "jwt"
    session_id: str | None = None
    expires_at: datetime | None = None

    @classmethod
    def from_jwt_claims(
        cls,
        claims: dict[str, Any],
        auth_method: Literal["jwt", "oauth2", "ldap", "apikey", "db"] = "jwt",
    ) -> Principal:
        """Create Principal from JWT claims.

        Args:
            claims: JWT claims dictionary.
            auth_method: Authentication method override.

        Returns:
            Principal instance populated from claims.

        Standard JWT claims mapped:
            - sub → user_id
            - preferred_username / name / sub → username
            - realm_access.roles / roles → roles
            - exp → expires_at
        """
        user_id = claims.get("sub", claims.get("user_id", ""))

        # Try various username claims
        username = (
            claims.get("preferred_username")
            or claims.get("email")
            or claims.get("name")
            or user_id
        )

        # Extract roles (Keycloak style or simple array)
        # Coerce to strings to handle non-string values from IdPs
        roles: set[str] = set()
        if "realm_access" in claims and isinstance(claims["realm_access"], dict):
            roles.update(str(r) for r in claims["realm_access"].get("roles", []))
        if "roles" in claims and isinstance(claims["roles"], list):
            roles.update(str(r) for r in claims["roles"])
        if "groups" in claims and isinstance(claims["groups"], list):
            roles.update(str(g) for g in claims["groups"])

        # Extract permissions (coerce to strings for type safety)
        permissions: set[str] = set()
        if "permissions" in claims and isinstance(claims["permissions"], list):
            permissions.update(str(p) for p in claims["permissions"])

        # Parse expiration
        expires_at: datetime | None = None
        if "exp" in claims:
            with contextlib.suppress(TypeError, ValueError):
                expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)

        return cls(
            user_id=str(user_id),
            username=str(username),
            roles=frozenset(roles),
            permissions=frozenset(permissions),
            claims=claims,
            tenant_id=claims.get("tenant_id") or claims.get("tenant"),
            mfa_verified=claims.get("mfa_verified", False),
            auth_method=auth_method,
            session_id=claims.get("session_id") or claims.get("sid"),
            expires_at=expires_at,
        )

    @classmethod
    def from_oauth_introspection(cls, data: dict[str, Any]) -> Principal:
        """Create Principal from OAuth2 token introspection response.

        Args:
            data: Introspection response from OAuth2 server.

        Returns:
            Principal instance populated from introspection data.
        """
        user_id = data.get("sub", data.get("user_id", ""))
        username = data.get("username", data.get("preferred_username", user_id))

        # Extract roles (coerce to strings for type safety)
        roles: set[str] = set()
        if "roles" in data and isinstance(data["roles"], list):
            roles.update(str(r) for r in data["roles"])

        # Extract permissions (coerce to strings for type safety)
        permissions: set[str] = set()
        if "permissions" in data and isinstance(data["permissions"], list):
            permissions.update(str(p) for p in data["permissions"])

        expires_at: datetime | None = None
        if "exp" in data:
            with contextlib.suppress(TypeError, ValueError):
                expires_at = datetime.fromtimestamp(data["exp"], tz=timezone.utc)

        return cls(
            user_id=str(user_id),
            username=str(username),
            roles=frozenset(roles),
            permissions=frozenset(permissions),
            claims=data,
            tenant_id=data.get("tenant_id"),
            mfa_verified=data.get("mfa_verified", False),
            auth_method="oauth2",
            expires_at=expires_at,
        )

    @classmethod
    def anonymous(cls) -> Principal:
        """Create anonymous Principal for unauthenticated users.

        Returns:
            Principal representing an anonymous/unauthenticated user.
        """
        return cls(user_id="anonymous", username="anonymous", auth_method="jwt")

    @classmethod
    def system(cls) -> Principal:
        """Create system Principal for internal processes.

        System principal has wildcard role/permission for internal operations
        that bypass normal authorization checks.

        Returns:
            Principal with full privileges for system operations.
        """
        return cls(
            user_id="system",
            username="system",
            roles=frozenset(["*"]),
            permissions=frozenset(["*"]),
            auth_method="jwt",
        )

    @property
    def is_authenticated(self) -> bool:
        """Check if this principal represents an authenticated user.

        Returns:
            True if the user is authenticated (not anonymous or system).
        """
        return self.user_id not in ("anonymous", "system")

    @property
    def is_expired(self) -> bool:
        """Check if the principal has expired.

        Uses timezone-aware comparison. Naive datetime is treated as UTC.

        Returns:
            True if expires_at is set and in the past.
        """
        if self.expires_at is None:
            return False

        # Use timezone-aware comparison (utcnow() deprecated in Python 3.12+)
        now = datetime.now(timezone.utc)
        expires_at = self.expires_at

        # Handle naive datetime (assume UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return now > expires_at

    @property
    def is_anonymous(self) -> bool:
        """Check if this principal is anonymous.

        Returns:
            True if the principal represents an anonymous user.
        """
        return self.user_id == "anonymous"

    @property
    def is_system(self) -> bool:
        """Check if this principal is the system user.

        Returns:
            True if the principal represents the system.
        """
        return self.user_id == "system"

    def has_role(self, role: str) -> bool:
        """Check if principal has a specific role.

        Wildcard role "*" matches all roles.

        Args:
            role: Role name to check.

        Returns:
            True if the principal has the role or wildcard.
        """
        return role in self.roles or "*" in self.roles

    def has_any_role(self, *roles: str) -> bool:
        """Check if principal has any of the specified roles.

        Args:
            *roles: Role names to check.

        Returns:
            True if the principal has at least one role.
        """
        return any(self.has_role(role) for role in roles)

    def has_all_roles(self, *roles: str) -> bool:
        """Check if principal has all of the specified roles.

        Args:
            *roles: Role names to check.

        Returns:
            True if the principal has all roles.
        """
        return all(self.has_role(role) for role in roles)

    def has_permission(self, permission: str) -> bool:
        """Check if principal has a specific permission.

        Wildcard permission "*" matches all permissions.

        Args:
            permission: Permission string to check (e.g., "read:orders").

        Returns:
            True if the principal has the permission or wildcard.
        """
        return permission in self.permissions or "*" in self.permissions

    def has_any_permission(self, *permissions: str) -> bool:
        """Check if principal has any of the specified permissions.

        Args:
            *permissions: Permission strings to check.

        Returns:
            True if the principal has at least one permission.
        """
        return any(self.has_permission(perm) for perm in permissions)

    def has_all_permissions(self, *permissions: str) -> bool:
        """Check if principal has all of the specified permissions.

        Args:
            *permissions: Permission strings to check.

        Returns:
            True if the principal has all permissions.
        """
        return all(self.has_permission(perm) for perm in permissions)

    def with_mfa_verified(self) -> Principal:
        """Return a new Principal with MFA verified flag set.

        Since Principal is immutable, this returns a new instance.

        Returns:
            New Principal with mfa_verified=True.
        """
        return self.model_copy(update={"mfa_verified": True})

    def with_roles(self, *additional_roles: str) -> Principal:
        """Return a new Principal with additional roles.

        Since Principal is immutable, this returns a new instance.

        Args:
            *additional_roles: Role names to add.

        Returns:
            New Principal with combined roles.
        """
        new_roles = self.roles | frozenset(additional_roles)
        return self.model_copy(update={"roles": new_roles})

    def with_permissions(self, *additional_permissions: str) -> Principal:
        """Return a new Principal with additional permissions.

        Since Principal is immutable, this returns a new instance.

        Args:
            *additional_permissions: Permission strings to add.

        Returns:
            New Principal with combined permissions.
        """
        new_permissions = self.permissions | frozenset(additional_permissions)
        return self.model_copy(update={"permissions": new_permissions})

    def __hash__(self) -> int:
        """Hash principal based on identifying fields.

        We exclude `claims` from hashing because dicts are unhashable.
        The hash is based on user_id, username, roles, permissions, and tenant_id.
        """
        hashable_data = (
            self.user_id,
            self.username,
            tuple(sorted(self.roles)),
            tuple(sorted(self.permissions)),
            self.tenant_id,
            self.mfa_verified,
            self.auth_method,
            self.session_id,
        )
        return hash(hashable_data)


__all__: list[str] = ["Principal"]
