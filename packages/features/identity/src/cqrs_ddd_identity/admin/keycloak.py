"""Keycloak Admin Adapter for user and role management.

Implements IIdentityProviderAdmin for Keycloak using python-keycloak.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakError

from ..exceptions import IdentityError
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

# ═══════════════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════════════


class UserManagementError(IdentityError):
    """Raised when user management operation fails."""


class UserNotFoundError(IdentityError):
    """Raised when a user is not found."""


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class KeycloakAdminConfig:
    """Configuration for Keycloak Admin adapter.

    Supports two authentication methods:
    1. Service account (recommended): client_id + client_secret
    2. Admin credentials: admin_username + admin_password

    Attributes:
        server_url: Keycloak server URL.
        realm: Realm to manage.
        client_id: Client ID for service account auth.
        client_secret: Client secret for service account auth.
        admin_username: Admin username for credential auth.
        admin_password: Admin password for credential auth.
        verify: Verify SSL certificates.
    """

    server_url: str
    realm: str
    client_id: str = "admin-cli"
    client_secret: str | None = None
    admin_username: str | None = None
    admin_password: str | None = None
    verify: bool = True


# ═══════════════════════════════════════════════════════════════
# KEYCLOAK ADMIN ADAPTER
# ═══════════════════════════════════════════════════════════════


class KeycloakAdminAdapter(IIdentityProviderAdmin, IGroupRolesCapability):
    """Keycloak implementation of IIdentityProviderAdmin.

    Also implements IGroupRolesCapability since Keycloak supports
    assigning roles to groups.

    Uses python-keycloak's KeycloakAdmin for administrative operations.

    Example:
        ```python
        config = KeycloakAdminConfig(
            server_url="https://keycloak.example.com",
            realm="my-realm",
            client_id="admin-cli",
            client_secret="admin-secret",
        )
        admin = KeycloakAdminAdapter(config)

        # Create user
        user_id = await admin.create_user(CreateUserData(
            username="newuser",
            email="user@example.com",
        ))

        # Assign roles
        await admin.assign_roles(user_id, ["app-user"])

        # Keycloak-specific: get group roles
        if isinstance(admin, IGroupRolesCapability):
            group_roles = await admin.get_group_roles(group_id)
        ```
    """

    def __init__(self, config: KeycloakAdminConfig) -> None:
        """Initialize Keycloak admin adapter.

        Args:
            config: Keycloak admin configuration.
        """
        self.config = config
        self._admin = self._create_admin_client()

    def _create_admin_client(self) -> KeycloakAdmin:
        """Create KeycloakAdmin client based on configuration."""
        if self.config.admin_username and self.config.admin_password:
            # Use admin user credentials
            return KeycloakAdmin(
                server_url=self.config.server_url,
                username=self.config.admin_username,
                password=self.config.admin_password,
                realm_name=self.config.realm,
                verify=self.config.verify,
            )
        # Use service account (client credentials)
        return KeycloakAdmin(
            server_url=self.config.server_url,
            client_id=self.config.client_id,
            client_secret_key=self.config.client_secret,
            realm_name=self.config.realm,
            verify=self.config.verify,
        )

    # ═══════════════════════════════════════════════════════════════
    # USER CRUD
    # ═══════════════════════════════════════════════════════════════

    async def create_user(self, user: CreateUserData) -> str:
        """Create a new user in Keycloak."""
        try:
            payload: dict[str, Any] = {
                "username": user.username,
                "email": user.email,
                "firstName": user.first_name,
                "lastName": user.last_name,
                "enabled": user.enabled,
                "emailVerified": user.email_verified,
            }

            if user.attributes:
                payload["attributes"] = user.attributes

            if user.temporary_password:
                payload["credentials"] = [
                    {
                        "type": "password",
                        "value": user.temporary_password,
                        "temporary": True,
                    }
                ]

            return str(self._admin.create_user(payload, exist_ok=False))

        except KeycloakError as e:
            raise UserManagementError(str(e)) from e

    async def get_user(self, user_id: str) -> UserData | None:
        """Get user by ID."""
        try:
            kc_user = self._admin.get_user(user_id)
            return self._map_user(kc_user)
        except KeycloakError:
            return None

    async def get_user_by_username(self, username: str) -> UserData | None:
        """Get user by username."""
        try:
            users = self._admin.get_users({"username": username, "exact": True})
            if users:
                return self._map_user(users[0])
            return None
        except KeycloakError:
            return None

    async def get_user_by_email(self, email: str) -> UserData | None:
        """Get user by email."""
        try:
            users = self._admin.get_users({"email": email, "exact": True})
            if users:
                return self._map_user(users[0])
            return None
        except KeycloakError:
            return None

    async def update_user(self, user_id: str, updates: UpdateUserData) -> None:
        """Update user attributes."""
        try:
            payload = self._build_update_payload(updates)

            if payload:
                self._admin.update_user(user_id, payload)

        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    def _build_update_payload(self, updates: UpdateUserData) -> dict[str, Any]:
        """Build update payload from UpdateUserData."""
        payload: dict[str, Any] = {}

        if updates.email is not None:
            payload["email"] = updates.email
        if updates.first_name is not None:
            payload["firstName"] = updates.first_name
        if updates.last_name is not None:
            payload["lastName"] = updates.last_name
        if updates.enabled is not None:
            payload["enabled"] = updates.enabled
        if updates.email_verified is not None:
            payload["emailVerified"] = updates.email_verified
        if updates.attributes is not None:
            payload["attributes"] = updates.attributes

        return payload

    async def delete_user(self, user_id: str) -> None:
        """Delete a user."""
        try:
            self._admin.delete_user(user_id)
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    async def list_users(self, filters: UserFilters | None = None) -> list[UserData]:
        """List users with optional filters."""
        try:
            params: dict[str, Any] = {}

            if filters:
                if filters.search:
                    params["search"] = filters.search
                if filters.enabled is not None:
                    params["enabled"] = "true" if filters.enabled else "false"
                params["first"] = filters.offset
                params["max"] = filters.limit

            users = self._admin.get_users(params)
            return [self._map_user(u) for u in users]

        except KeycloakError as e:
            raise UserManagementError(str(e)) from e

    async def count_users(self, filters: UserFilters | None = None) -> int:
        """Count users matching filters."""
        try:
            params: dict[str, Any] = {}

            if filters and filters.search:
                params["search"] = filters.search

            return int(self._admin.users_count(params))

        except KeycloakError as e:
            raise UserManagementError(str(e)) from e

    # ═══════════════════════════════════════════════════════════════
    # PASSWORD MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def set_password(
        self, user_id: str, password: str, temporary: bool = False
    ) -> None:
        """Set user's password."""
        try:
            self._admin.set_user_password(user_id, password, temporary=temporary)
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    async def send_password_reset(self, user_id: str) -> None:
        """Trigger password reset email."""
        try:
            self._admin.send_update_account(
                user_id, ["UPDATE_PASSWORD"], lifespan=86400
            )
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    async def send_verify_email(self, user_id: str) -> None:
        """Send email verification email."""
        try:
            self._admin.send_verify_email(user_id)
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    # ═══════════════════════════════════════════════════════════════
    # ROLE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def list_roles(self) -> list[RoleData]:
        """List all realm roles."""
        try:
            roles = self._admin.get_realm_roles()
            return [self._map_role(r) for r in roles]
        except KeycloakError as e:
            raise UserManagementError(str(e)) from e

    async def get_user_roles(self, user_id: str) -> list[RoleData]:
        """Get user's assigned realm roles."""
        try:
            roles = self._admin.get_realm_roles_of_user(user_id)
            return [self._map_role(r) for r in roles]
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    async def assign_roles(self, user_id: str, role_names: list[str]) -> None:
        """Assign realm roles to user."""
        try:
            # Get role representations
            roles = []
            for name in role_names:
                role = self._admin.get_realm_role(name)
                roles.append({"id": role["id"], "name": role["name"]})

            self._admin.assign_realm_roles(user_id, roles)

        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    async def remove_roles(self, user_id: str, role_names: list[str]) -> None:
        """Remove realm roles from user."""
        try:
            # Get role representations
            roles = []
            for name in role_names:
                role = self._admin.get_realm_role(name)
                roles.append({"id": role["id"], "name": role["name"]})

            self._admin.delete_realm_roles_of_user(user_id, roles)

        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    # ═══════════════════════════════════════════════════════════════
    # GROUP MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def list_groups(self) -> list[GroupData]:
        """List all groups (hierarchical)."""
        try:
            groups = self._admin.get_groups()
            return [self._map_group(g) for g in groups]
        except KeycloakError as e:
            raise UserManagementError(str(e)) from e

    async def get_user_groups(self, user_id: str) -> list[GroupData]:
        """Get groups the user belongs to."""
        try:
            groups = self._admin.get_user_groups(user_id)
            return [self._map_group(g) for g in groups]
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    async def add_to_groups(self, user_id: str, group_ids: list[str]) -> None:
        """Add user to groups."""
        try:
            for group_id in group_ids:
                self._admin.group_user_add(user_id, group_id)
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    async def remove_from_groups(self, user_id: str, group_ids: list[str]) -> None:
        """Remove user from groups."""
        try:
            for group_id in group_ids:
                self._admin.group_user_remove(user_id, group_id)
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    # ═══════════════════════════════════════════════════════════════
    # GROUP ROLES CAPABILITY
    # ═══════════════════════════════════════════════════════════════

    async def get_group_roles(self, group_id: str) -> list[RoleData]:
        """Get roles assigned to a group."""
        try:
            roles = self._admin.get_group_realm_roles(group_id)
            return [self._map_role(r) for r in roles]
        except KeycloakError as e:
            raise UserManagementError(str(e)) from e

    async def assign_group_roles(self, group_id: str, role_names: list[str]) -> None:
        """Assign realm roles to a group."""
        try:
            # Get role representations
            roles = []
            for name in role_names:
                role = self._admin.get_realm_role(name)
                roles.append({"id": role["id"], "name": role["name"]})

            self._admin.assign_group_realm_roles(group_id, roles)

        except KeycloakError as e:
            raise UserManagementError(str(e)) from e

    async def remove_group_roles(self, group_id: str, role_names: list[str]) -> None:
        """Remove realm roles from a group."""
        try:
            # Get role representations
            roles = []
            for name in role_names:
                role = self._admin.get_realm_role(name)
                roles.append({"id": role["id"], "name": role["name"]})

            self._admin.delete_group_realm_roles(group_id, roles)

        except KeycloakError as e:
            raise UserManagementError(str(e)) from e

    # ═══════════════════════════════════════════════════════════════
    # SESSION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def get_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Get active sessions for a user."""
        try:
            return list[dict[str, Any]](self._admin.get_sessions(user_id))
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    async def logout_user(self, user_id: str) -> None:
        """Logout user from all sessions."""
        try:
            self._admin.user_logout(user_id)
        except KeycloakError as e:
            if "404" in str(e):
                raise UserNotFoundError(f"User {user_id} not found") from e
            raise UserManagementError(str(e)) from e

    async def revoke_user_session(self, session_id: str) -> None:
        """Revoke a specific user session."""
        # python-keycloak may expose this as user_logout_all_session or delete_session
        revoke = getattr(
            self._admin,
            "user_logout_all_session",
            getattr(self._admin, "delete_session", None),
        )
        if revoke is None:
            raise UserManagementError(
                "This KeycloakAdmin version does not support revoking a session by id"
            )
        try:
            revoke(session_id)
        except KeycloakError as e:
            raise UserManagementError(str(e)) from e

    # ═══════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═══════════════════════════════════════════════════════════════

    def _map_user(self, kc_user: dict[str, Any]) -> UserData:
        """Map Keycloak user dict to UserData."""
        return UserData(
            user_id=kc_user.get("id", ""),
            username=kc_user.get("username", ""),
            email=kc_user.get("email", ""),
            first_name=kc_user.get("firstName", ""),
            last_name=kc_user.get("lastName", ""),
            enabled=kc_user.get("enabled", True),
            email_verified=kc_user.get("emailVerified", False),
            created_at=kc_user.get("createdTimestamp"),
            attributes=kc_user.get("attributes", {}),
        )

    def _map_role(self, kc_role: dict[str, Any]) -> RoleData:
        """Map Keycloak role dict to RoleData."""
        return RoleData(
            role_id=kc_role.get("id", ""),
            name=kc_role.get("name", ""),
            description=kc_role.get("description", ""),
            is_composite=kc_role.get("composite", False),
        )

    def _map_group(self, kc_group: dict[str, Any]) -> GroupData:
        """Map Keycloak group dict to GroupData."""
        return GroupData(
            group_id=kc_group.get("id", ""),
            name=kc_group.get("name", ""),
            parent_id=kc_group.get("parentId"),
            path=kc_group.get("path"),
            attributes=kc_group.get("attributes", {}),
        )
