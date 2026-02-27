"""Admin module for identity provider administration.

Provides ports and adapters for user management, role assignment,
and group management operations separate from authentication.
"""

from __future__ import annotations

from .ports import (
    CreateUserData,
    GroupData,
    IGroupRolesCapability,
    IIdentityProviderAdmin,
    RoleData,
    UpdateUserData,
    UserData,
    UserFilters,
)

# Keycloak admin (requires [keycloak] extra)
try:
    from .keycloak import (
        KeycloakAdminAdapter,
        KeycloakAdminConfig,
        UserManagementError,
        UserNotFoundError,
    )
except ImportError:
    # python-keycloak not installed
    KeycloakAdminAdapter = None  # type: ignore[misc,assignment]
    KeycloakAdminConfig = None  # type: ignore[misc,assignment]
    UserManagementError = None  # type: ignore[misc,assignment]
    UserNotFoundError = None  # type: ignore[misc,assignment]

__all__: list[str] = [
    # Ports
    "IIdentityProviderAdmin",
    "IGroupRolesCapability",
    # DTOs
    "CreateUserData",
    "UpdateUserData",
    "UserData",
    "RoleData",
    "GroupData",
    "UserFilters",
    # Keycloak (optional)
    "KeycloakAdminAdapter",
    "KeycloakAdminConfig",
    "UserManagementError",
    "UserNotFoundError",
]
