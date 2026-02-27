"""Integration tests for Keycloak admin adapter."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest

from cqrs_ddd_identity.admin.keycloak import UserManagementError
from cqrs_ddd_identity.admin.ports import (
    CreateUserData,
    UpdateUserData,
    UserFilters,
)

if TYPE_CHECKING:
    from cqrs_ddd_identity.admin import KeycloakAdminAdapter


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_get_user_by_username(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test retrieving a user by username."""
    # Get admin user (exists by default in master realm)
    user = await keycloak_admin_adapter.get_user_by_username("admin")

    assert user is not None
    assert user.username == "admin"
    assert user.user_id is not None
    assert user.enabled is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_list_users(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test listing users."""
    users = await keycloak_admin_adapter.list_users()

    assert users is not None
    assert len(users) >= 1
    # At least admin user should exist
    admin_user = next((u for u in users if u.username == "admin"), None)
    assert admin_user is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_create_update_delete_user(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test CRUD operations for users."""
    # Create a user
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="test-user-123",
            email="test@example.com",
            first_name="Test",
            last_name="User",
            enabled=True,
            temporary_password="password123",
        )
    )

    assert user_id is not None

    # Get the user
    user = await keycloak_admin_adapter.get_user(user_id)
    assert user is not None
    assert user.username == "test-user-123"
    assert user.email == "test@example.com"

    # Update the user
    await keycloak_admin_adapter.update_user(
        user_id,
        UpdateUserData(first_name="Updated", last_name="Name"),
    )

    # Verify update
    updated_user = await keycloak_admin_adapter.get_user(user_id)
    assert updated_user is not None
    assert updated_user.first_name == "Updated"
    assert updated_user.last_name == "Name"

    # Delete the user
    await keycloak_admin_adapter.delete_user(user_id)

    # Verify deletion
    deleted_user = await keycloak_admin_adapter.get_user(user_id)
    assert deleted_user is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_set_password(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test setting a user password."""
    # Create a user
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="password-test-user",
            email="password@example.com",
            enabled=True,
            temporary_password="oldpassword",
        )
    )

    # Update password
    await keycloak_admin_adapter.set_password(
        user_id=user_id,
        password="newpassword123",
    )

    # Cleanup
    await keycloak_admin_adapter.delete_user(user_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_list_roles(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test listing available roles."""
    roles = await keycloak_admin_adapter.list_roles()

    assert roles is not None
    assert len(roles) >= 1
    # Default roles should exist
    default_role = next((r for r in roles if r.name == "uma_authorization"), None)
    assert default_role is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_user_roles(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test assigning and removing roles from a user."""
    # Create a user
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="role-test-user",
            email="role@example.com",
            enabled=True,
        )
    )

    # List available roles
    roles = await keycloak_admin_adapter.list_roles()
    assert len(roles) > 0

    # Assign first available role to user
    test_role = roles[0]
    await keycloak_admin_adapter.assign_roles(
        user_id=user_id,
        role_names=[test_role.name],
    )

    # Get user roles
    user_roles = await keycloak_admin_adapter.get_user_roles(user_id)
    assert test_role.name in [r.name for r in user_roles]

    # Remove role from user
    await keycloak_admin_adapter.remove_roles(
        user_id=user_id,
        role_names=[test_role.name],
    )

    # Verify removal
    user_roles_after = await keycloak_admin_adapter.get_user_roles(user_id)
    assert test_role.name not in [r.name for r in user_roles_after]

    # Cleanup
    await keycloak_admin_adapter.delete_user(user_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_list_groups(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test listing groups."""
    groups = await keycloak_admin_adapter.list_groups()

    assert groups is not None
    # May be empty in fresh Keycloak, but should not error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_count_users(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test counting users."""
    count = await keycloak_admin_adapter.count_users()

    assert count is not None
    assert count >= 1  # At least admin user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_user_not_found(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test behavior when user doesn't exist."""
    user = await keycloak_admin_adapter.get_user("non-existent-id")
    assert user is None

    user = await keycloak_admin_adapter.get_user_by_username("nonexistent")
    assert user is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_get_user_by_email(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test retrieving a user by email."""
    # Admin user exists with email (Keycloak may set it)
    users = await keycloak_admin_adapter.list_users()
    admin_user = next((u for u in users if u.username == "admin"), None)
    assert admin_user is not None
    if admin_user.email:
        by_email = await keycloak_admin_adapter.get_user_by_email(admin_user.email)
        assert by_email is not None
        assert by_email.user_id == admin_user.user_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_list_users_with_filters(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test listing users with UserFilters."""
    filters = UserFilters(search="admin", limit=5, offset=0, enabled=True)
    users = await keycloak_admin_adapter.list_users(filters)
    assert users is not None
    assert len(users) <= 5
    admin_user = next((u for u in users if u.username == "admin"), None)
    assert admin_user is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_send_password_reset(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test sending password reset email (skipped if Keycloak email/SMTP not configured)."""
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="reset-test-user",
            email="reset@example.com",
            enabled=True,
            temporary_password="initial",
        )
    )
    try:
        try:
            await keycloak_admin_adapter.send_password_reset(user_id)
        except UserManagementError as e:
            if "500" in str(e):
                pytest.skip("Keycloak email/SMTP not configured")
            raise
    finally:
        await keycloak_admin_adapter.delete_user(user_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_send_verify_email(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test sending email verification (skipped if Keycloak email/SMTP not configured)."""
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="verify-email-user",
            email="verify@example.com",
            enabled=True,
        )
    )
    try:
        try:
            await keycloak_admin_adapter.send_verify_email(user_id)
        except UserManagementError as e:
            if "500" in str(e):
                pytest.skip("Keycloak email/SMTP not configured")
            raise
    finally:
        await keycloak_admin_adapter.delete_user(user_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_get_user_groups(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test getting groups for a user."""
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="groups-test-user",
            email="groups@example.com",
            enabled=True,
        )
    )
    try:
        groups = await keycloak_admin_adapter.get_user_groups(user_id)
        assert groups is not None
        assert isinstance(groups, list)
    finally:
        await keycloak_admin_adapter.delete_user(user_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_add_remove_user_from_groups(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test adding and removing user from groups."""
    # Clean up existing group if present
    try:
        existing = keycloak_admin_adapter._admin.get_group_by_path(
            "integration-test-group"
        )
        if existing:
            keycloak_admin_adapter._admin.delete_group(existing["id"])
    except Exception:
        pass

    # Create user
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="group-member-user",
            email="groupmember@example.com",
            enabled=True,
        )
    )

    # Create group
    group_id = keycloak_admin_adapter._admin.create_group(
        {"name": "integration-test-group"}
    )

    if not group_id:
        await keycloak_admin_adapter.delete_user(user_id)
        pytest.fail("create_group did not return group id")
    try:
        await keycloak_admin_adapter.add_to_groups(user_id, [group_id])
        user_groups = await keycloak_admin_adapter.get_user_groups(user_id)
        assert any(g.group_id == group_id for g in user_groups)
        await keycloak_admin_adapter.remove_from_groups(user_id, [group_id])
        user_groups_after = await keycloak_admin_adapter.get_user_groups(user_id)
        assert not any(g.group_id == group_id for g in user_groups_after)
    finally:
        await keycloak_admin_adapter.delete_user(user_id)
        with contextlib.suppress(Exception):
            keycloak_admin_adapter._admin.delete_group(group_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_get_group_roles(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test getting roles assigned to a group."""
    # Clean up existing group if present
    try:
        existing = keycloak_admin_adapter._admin.get_group_by_path("roles-test-group")
        if existing:
            keycloak_admin_adapter._admin.delete_group(existing["id"])
    except Exception:
        pass

    # Create group
    group_id = keycloak_admin_adapter._admin.create_group({"name": "roles-test-group"})

    if not group_id:
        pytest.fail("create_group did not return group id")
    try:
        roles = await keycloak_admin_adapter.get_group_roles(group_id)
        assert roles is not None
        assert isinstance(roles, list)
    finally:
        with contextlib.suppress(Exception):
            keycloak_admin_adapter._admin.delete_group(group_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_assign_remove_group_roles(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test assigning and removing roles from a group."""
    # Clean up existing group if present
    try:
        existing = keycloak_admin_adapter._admin.get_group_by_path("group-roles-test")
        if existing:
            keycloak_admin_adapter._admin.delete_group(existing["id"])
    except Exception:
        pass

    # Create group
    group_id = keycloak_admin_adapter._admin.create_group({"name": "group-roles-test"})

    if not group_id:
        pytest.fail("create_group did not return group id")

    # Get realm roles
    realm_roles = await keycloak_admin_adapter.list_roles()
    if not realm_roles:
        pytest.skip("No realm roles available")
    role_name = realm_roles[0].name
    try:
        await keycloak_admin_adapter.assign_group_roles(group_id, [role_name])
        group_roles = await keycloak_admin_adapter.get_group_roles(group_id)
        assert any(r.name == role_name for r in group_roles)
        await keycloak_admin_adapter.remove_group_roles(group_id, [role_name])
        group_roles_after = await keycloak_admin_adapter.get_group_roles(group_id)
        assert not any(r.name == role_name for r in group_roles_after)
    finally:
        with contextlib.suppress(Exception):
            keycloak_admin_adapter._admin.delete_group(group_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_get_user_sessions(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test getting active sessions for a user."""
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="sessions-test-user",
            email="sessions@example.com",
            enabled=True,
        )
    )
    try:
        sessions = await keycloak_admin_adapter.get_user_sessions(user_id)
        assert sessions is not None
        assert isinstance(sessions, list)
    finally:
        await keycloak_admin_adapter.delete_user(user_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_logout_user(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test logging out a user from all sessions."""
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="logout-test-user",
            email="logout@example.com",
            enabled=True,
            temporary_password="pass",
        )
    )
    try:
        await keycloak_admin_adapter.logout_user(user_id)
        sessions = await keycloak_admin_adapter.get_user_sessions(user_id)
        assert isinstance(sessions, list)
    finally:
        await keycloak_admin_adapter.delete_user(user_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_admin_revoke_user_session(
    keycloak_admin_adapter: KeycloakAdminAdapter,
):
    """Test revoking a specific session (no-op if no sessions)."""
    user_id = await keycloak_admin_adapter.create_user(
        CreateUserData(
            username="revoke-session-user",
            email="revoke@example.com",
            enabled=True,
        )
    )
    try:
        sessions = await keycloak_admin_adapter.get_user_sessions(user_id)
        if sessions and len(sessions) > 0:
            session_id = (
                sessions[0].get("id")
                if isinstance(sessions[0], dict)
                else getattr(sessions[0], "id", None)
            )
            if session_id:
                await keycloak_admin_adapter.revoke_user_session(session_id)
        else:
            # No sessions: call with a dummy id; Keycloak may return error, we just ensure no crash
            with contextlib.suppress(Exception):
                await keycloak_admin_adapter.revoke_user_session("dummy-session-id")
    finally:
        await keycloak_admin_adapter.delete_user(user_id)
