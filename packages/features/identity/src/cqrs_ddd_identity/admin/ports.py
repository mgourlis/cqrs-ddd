"""Admin ports for identity provider administration.

These protocols define interfaces for administrative operations
such as user management, role assignment, and group management.
Separate from authentication (IIdentityProvider).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ═══════════════════════════════════════════════════════════════
# DATA TRANSFER OBJECTS
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CreateUserData:
    """Data for creating a new user.

    Attributes:
        username: Unique username.
        email: User's email address.
        first_name: User's first name.
        last_name: User's last name.
        enabled: Whether the user account is enabled.
        email_verified: Whether the email has been verified.
        attributes: Custom attributes (IdP-specific).
        temporary_password: Optional password that user must change on first login.
    """

    username: str
    email: str
    first_name: str = ""
    last_name: str = ""
    enabled: bool = True
    email_verified: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)
    temporary_password: str | None = None


@dataclass
class UpdateUserData:
    """Data for updating an existing user.

    All fields are optional - only provided fields will be updated.
    None values are ignored (not unset).

    Attributes:
        email: New email address.
        first_name: New first name.
        last_name: New last name.
        enabled: Enable/disable account.
        email_verified: Mark email as verified.
        attributes: Replace custom attributes.
    """

    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    enabled: bool | None = None
    email_verified: bool | None = None
    attributes: dict[str, Any] | None = None


@dataclass(frozen=True)
class UserData:
    """User data returned from IdP.

    Attributes:
        user_id: Unique user identifier in the IdP.
        username: Username.
        email: Email address.
        first_name: First name.
        last_name: Last name.
        enabled: Whether account is enabled.
        email_verified: Whether email is verified.
        created_at: Account creation timestamp (IdP-specific format).
        attributes: Custom attributes from IdP.
    """

    user_id: str
    username: str
    email: str
    first_name: str = ""
    last_name: str = ""
    enabled: bool = True
    email_verified: bool = False
    created_at: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoleData:
    """Role data from IdP.

    Attributes:
        role_id: Unique role identifier.
        name: Role name.
        description: Human-readable description.
        is_composite: Whether this role is composed of other roles.
    """

    role_id: str
    name: str
    description: str = ""
    is_composite: bool = False


@dataclass(frozen=True)
class GroupData:
    """Group data from IdP.

    Groups are supported by most identity providers but with varying
    semantics. This provides a generic representation.

    Hierarchy support varies:
    - Some IdPs support nested groups (parent_id points to parent)
    - Some IdPs support path-based hierarchy (path as IdP-specific string)
    - Some IdPs have flat groups (parent_id is None)

    Attributes:
        group_id: Unique group identifier.
        name: Group name.
        parent_id: Parent group ID for hierarchy (if supported).
        path: IdP-specific path format (e.g., "/web/admin").
        attributes: Custom attributes from IdP.
    """

    group_id: str
    name: str
    parent_id: str | None = None
    path: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UserFilters:
    """Filters for listing users.

    Attributes:
        search: Search in username, email, name fields.
        role: Filter by assigned role name.
        group: Filter by group membership.
        enabled: Filter by enabled status.
        offset: Pagination offset.
        limit: Maximum results to return.
    """

    search: str | None = None
    role: str | None = None
    group: str | None = None
    enabled: bool | None = None
    offset: int = 0
    limit: int = 100


# ═══════════════════════════════════════════════════════════════
# IDENTITY PROVIDER ADMIN PORT
# ═══════════════════════════════════════════════════════════════


@runtime_checkable
class IIdentityProviderAdmin(Protocol):
    """Protocol for administrative identity provider operations.

    Implementations: KeycloakAdminAdapter, Auth0AdminAdapter, etc.

    This port handles user management operations that require admin
    privileges on the identity provider, separate from regular authentication.

    All methods are async to support remote IdP API calls.
    """

    # ═══════════════════════════════════════════════════════════════
    # USER CRUD
    # ═══════════════════════════════════════════════════════════════

    async def create_user(self, user: CreateUserData) -> str:
        """Create a new user in the identity provider.

        Args:
            user: User data for creation.

        Returns:
            The created user's ID.

        Raises:
            UserManagementError: If creation fails (e.g., duplicate username).
        """
        ...

    async def get_user(self, user_id: str) -> UserData | None:
        """Get user by ID.

        Args:
            user_id: User's ID in the IdP.

        Returns:
            UserData if found, None otherwise.
        """
        ...

    async def get_user_by_username(self, username: str) -> UserData | None:
        """Get user by username.

        Args:
            username: User's username.

        Returns:
            UserData if found, None otherwise.
        """
        ...

    async def get_user_by_email(self, email: str) -> UserData | None:
        """Get user by email.

        Args:
            email: User's email address.

        Returns:
            UserData if found, None otherwise.
        """
        ...

    async def update_user(self, user_id: str, updates: UpdateUserData) -> None:
        """Update user attributes.

        Args:
            user_id: User's ID.
            updates: Fields to update (None values are ignored).

        Raises:
            UserNotFoundError: If user doesn't exist.
            UserManagementError: If update fails.
        """
        ...

    async def delete_user(self, user_id: str) -> None:
        """Delete a user.

        Args:
            user_id: User's ID to delete.

        Raises:
            UserNotFoundError: If user doesn't exist.
            UserManagementError: If deletion fails.
        """
        ...

    async def list_users(self, filters: UserFilters | None = None) -> list[UserData]:
        """List users with optional filters.

        Args:
            filters: Optional filtering criteria.

        Returns:
            List of matching users.
        """
        ...

    async def count_users(self, filters: UserFilters | None = None) -> int:
        """Count users matching filters.

        Args:
            filters: Optional filtering criteria.

        Returns:
            Total count of matching users.
        """
        ...

    # ═══════════════════════════════════════════════════════════════
    # PASSWORD MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def set_password(
        self, user_id: str, password: str, temporary: bool = False
    ) -> None:
        """Set user's password.

        Args:
            user_id: User's ID.
            password: New password.
            temporary: If True, user must change on next login.

        Raises:
            UserNotFoundError: If user doesn't exist.
            UserManagementError: If password set fails.
        """
        ...

    async def send_password_reset(self, user_id: str) -> None:
        """Trigger password reset email.

        Args:
            user_id: User's ID.

        Raises:
            UserNotFoundError: If user doesn't exist.
            UserManagementError: If sending fails.
        """
        ...

    async def send_verify_email(self, user_id: str) -> None:
        """Send email verification email.

        Args:
            user_id: User's ID.

        Raises:
            UserNotFoundError: If user doesn't exist.
            UserManagementError: If sending fails.
        """
        ...

    # ═══════════════════════════════════════════════════════════════
    # ROLE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def list_roles(self) -> list[RoleData]:
        """List all realm roles.

        Returns:
            List of all available roles.
        """
        ...

    async def get_user_roles(self, user_id: str) -> list[RoleData]:
        """Get user's assigned realm roles.

        Args:
            user_id: User's ID.

        Returns:
            List of roles assigned to the user.

        Raises:
            UserNotFoundError: If user doesn't exist.
        """
        ...

    async def assign_roles(self, user_id: str, role_names: list[str]) -> None:
        """Assign realm roles to user.

        Args:
            user_id: User's ID.
            role_names: Names of roles to assign.

        Raises:
            UserNotFoundError: If user doesn't exist.
            UserManagementError: If assignment fails.
        """
        ...

    async def remove_roles(self, user_id: str, role_names: list[str]) -> None:
        """Remove realm roles from user.

        Args:
            user_id: User's ID.
            role_names: Names of roles to remove.

        Raises:
            UserNotFoundError: If user doesn't exist.
            UserManagementError: If removal fails.
        """
        ...

    # ═══════════════════════════════════════════════════════════════
    # GROUP MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def list_groups(self) -> list[GroupData]:
        """List all groups (hierarchical).

        Returns:
            List of all groups with hierarchy information.
        """
        ...

    async def get_user_groups(self, user_id: str) -> list[GroupData]:
        """Get groups the user belongs to.

        Args:
            user_id: User's ID.

        Returns:
            List of groups the user is a member of.

        Raises:
            UserNotFoundError: If user doesn't exist.
        """
        ...

    async def add_to_groups(self, user_id: str, group_ids: list[str]) -> None:
        """Add user to groups.

        Args:
            user_id: User's ID.
            group_ids: IDs of groups to add user to.

        Raises:
            UserNotFoundError: If user doesn't exist.
            UserManagementError: If addition fails.
        """
        ...

    async def remove_from_groups(self, user_id: str, group_ids: list[str]) -> None:
        """Remove user from groups.

        Args:
            user_id: User's ID.
            group_ids: IDs of groups to remove user from.

        Raises:
            UserNotFoundError: If user doesn't exist.
            UserManagementError: If removal fails.
        """
        ...

    # ═══════════════════════════════════════════════════════════════
    # SESSION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def get_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Get active sessions for a user.

        Args:
            user_id: User's ID.

        Returns:
            List of session data (IdP-specific format).

        Raises:
            UserNotFoundError: If user doesn't exist.
        """
        ...

    async def logout_user(self, user_id: str) -> None:
        """Logout user from all sessions.

        Args:
            user_id: User's ID.

        Raises:
            UserNotFoundError: If user doesn't exist.
        """
        ...

    async def revoke_user_session(self, session_id: str) -> None:
        """Revoke a specific user session.

        Args:
            session_id: Session identifier to revoke.

        Raises:
            UserManagementError: If revocation fails.
        """
        ...


# ═══════════════════════════════════════════════════════════════
# OPTIONAL CAPABILITY PROTOCOLS
# ═══════════════════════════════════════════════════════════════


@runtime_checkable
class IGroupRolesCapability(Protocol):
    """Protocol for IdPs that support assigning roles to groups.

    In some identity providers (like Keycloak), groups can have roles
    assigned to them, and all group members inherit those roles.
    This is NOT a universal IdP feature.

    Usage:
        ```python
        if isinstance(idp_admin, IGroupRolesCapability):
            group_roles = await idp_admin.get_group_roles(group_id)
        ```
    """

    async def get_group_roles(self, group_id: str) -> list[RoleData]:
        """Get roles assigned to a group.

        Args:
            group_id: Group's ID.

        Returns:
            List of roles assigned to the group.
        """
        ...

    async def assign_group_roles(self, group_id: str, role_names: list[str]) -> None:
        """Assign realm roles to a group.

        Args:
            group_id: Group's ID.
            role_names: Names of roles to assign.
        """
        ...

    async def remove_group_roles(self, group_id: str, role_names: list[str]) -> None:
        """Remove realm roles from a group.

        Args:
            group_id: Group's ID.
            role_names: Names of roles to remove.
        """
        ...
