"""Unit tests for Keycloak Admin adapter (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from keycloak.exceptions import KeycloakError

from cqrs_ddd_identity.admin.keycloak import (
    KeycloakAdminAdapter,
    KeycloakAdminConfig,
    UserManagementError,
    UserNotFoundError,
)
from cqrs_ddd_identity.admin.ports import (
    CreateUserData,
    GroupData,
    RoleData,
    UpdateUserData,
    UserData,
    UserFilters,
)

# ═══════════════════════════════════════════════════════════════
# KeycloakAdminConfig
# ═══════════════════════════════════════════════════════════════


class TestKeycloakAdminConfig:
    """KeycloakAdminConfig and adapter init."""

    def test_init_with_admin_credentials_creates_client_with_username_password(
        self,
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_admin:
            mock_admin.return_value = MagicMock()
            config = KeycloakAdminConfig(
                server_url="https://kc.example.com",
                realm="master",
                admin_username="admin",
                admin_password="secret",
            )
            KeycloakAdminAdapter(config)
            mock_admin.assert_called_once()
            call_kw = mock_admin.call_args[1]
            assert call_kw["username"] == "admin"
            assert call_kw["password"] == "secret"
            assert (
                "client_secret_key" not in call_kw
                or call_kw.get("client_secret_key") is None
            )

    def test_init_with_client_secret_creates_client_with_client_credentials(
        self,
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_admin:
            mock_admin.return_value = MagicMock()
            config = KeycloakAdminConfig(
                server_url="https://kc.example.com",
                realm="master",
                client_id="admin-cli",
                client_secret="client-secret",
            )
            KeycloakAdminAdapter(config)
            mock_admin.assert_called_once()
            call_kw = mock_admin.call_args[1]
            assert call_kw["client_id"] == "admin-cli"
            assert call_kw["client_secret_key"] == "client-secret"


# ═══════════════════════════════════════════════════════════════
# Fixture
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def admin_config() -> KeycloakAdminConfig:
    return KeycloakAdminConfig(
        server_url="https://kc.example.com",
        realm="master",
        admin_username="admin",
        admin_password="admin",
    )


@pytest.fixture
def mock_admin(admin_config: KeycloakAdminConfig) -> KeycloakAdminAdapter:
    with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
        mock_kc.return_value = MagicMock()
        return KeycloakAdminAdapter(admin_config)


# ═══════════════════════════════════════════════════════════════
# User CRUD
# ═══════════════════════════════════════════════════════════════


class TestKeycloakAdminAdapterCreateUser:
    """create_user(CreateUserData)."""

    @pytest.mark.asyncio
    async def test_create_user_success_returns_user_id(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.create_user.return_value = "new-user-id"
            adapter = KeycloakAdminAdapter(admin_config)
            user = CreateUserData(
                username="alice",
                email="alice@example.com",
                first_name="Alice",
                last_name="User",
                enabled=True,
                temporary_password="pass123",
            )
            user_id = await adapter.create_user(user)
            assert user_id == "new-user-id"
            call_payload = mock_kc.return_value.create_user.call_args[0][0]
            assert call_payload["username"] == "alice"
            assert call_payload["email"] == "alice@example.com"
            assert call_payload["firstName"] == "Alice"
            assert "credentials" in call_payload
            assert call_payload["credentials"][0]["value"] == "pass123"

    @pytest.mark.asyncio
    async def test_create_user_keycloak_error_raises_user_management_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.create_user.side_effect = KeycloakError("User exists")
            adapter = KeycloakAdminAdapter(admin_config)
            user = CreateUserData(
                username="alice",
                email="alice@example.com",
            )
            with pytest.raises(UserManagementError, match="User exists"):
                await adapter.create_user(user)


class TestKeycloakAdminAdapterGetUser:
    """get_user(user_id)."""

    @pytest.mark.asyncio
    async def test_get_user_success_returns_user_data(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_user.return_value = {
                "id": "u1",
                "username": "alice",
                "email": "alice@example.com",
                "firstName": "Alice",
                "lastName": "U",
                "enabled": True,
            }
            adapter = KeycloakAdminAdapter(admin_config)
            user = await adapter.get_user("u1")
            assert user is not None
            assert user.user_id == "u1"
            assert user.username == "alice"

    @pytest.mark.asyncio
    async def test_get_user_keycloak_error_returns_none(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_user.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            user = await adapter.get_user("nonexistent")
            assert user is None


class TestKeycloakAdminAdapterGetUserByUsername:
    """get_user_by_username(username)."""

    @pytest.mark.asyncio
    async def test_get_user_by_username_success(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_users.return_value = [
                {"id": "u1", "username": "alice", "email": "a@b.com"}
            ]
            adapter = KeycloakAdminAdapter(admin_config)
            user = await adapter.get_user_by_username("alice")
            assert user is not None
            assert user.username == "alice"

    @pytest.mark.asyncio
    async def test_get_user_by_username_empty_returns_none(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_users.return_value = []
            adapter = KeycloakAdminAdapter(admin_config)
            user = await adapter.get_user_by_username("nonexistent")
            assert user is None


class TestKeycloakAdminAdapterGetUserByEmail:
    """get_user_by_email(email)."""

    @pytest.mark.asyncio
    async def test_get_user_by_email_success(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_users.return_value = [
                {"id": "u1", "username": "alice", "email": "alice@example.com"}
            ]
            adapter = KeycloakAdminAdapter(admin_config)
            user = await adapter.get_user_by_email("alice@example.com")
            assert user is not None
            assert user.email == "alice@example.com"


class TestKeycloakAdminAdapterUpdateUser:
    """update_user(user_id, updates)."""

    @pytest.mark.asyncio
    async def test_update_user_success(self, admin_config: KeycloakAdminConfig) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            adapter = KeycloakAdminAdapter(admin_config)
            await adapter.update_user(
                "u1",
                UpdateUserData(first_name="New", last_name="Name"),
            )
            mock_kc.return_value.update_user.assert_called_once()
            call_args = mock_kc.return_value.update_user.call_args
            assert call_args[0][0] == "u1"
            assert call_args[0][1]["firstName"] == "New"
            assert call_args[0][1]["lastName"] == "Name"

    @pytest.mark.asyncio
    async def test_update_user_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.update_user.side_effect = KeycloakError(
                "404 Not Found"
            )
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError, match="u99"):
                await adapter.update_user(
                    "u99",
                    UpdateUserData(first_name="X"),
                )


class TestKeycloakAdminAdapterDeleteUser:
    """delete_user(user_id)."""

    @pytest.mark.asyncio
    async def test_delete_user_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.delete_user.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.delete_user("nonexistent")


class TestKeycloakAdminAdapterListUsers:
    """list_users(filters?)."""

    @pytest.mark.asyncio
    async def test_list_users_with_filters(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_users.return_value = [
                {"id": "u1", "username": "alice", "email": "a@b.com"}
            ]
            adapter = KeycloakAdminAdapter(admin_config)
            filters = UserFilters(search="alice", limit=5, offset=0, enabled=True)
            users = await adapter.list_users(filters)
            assert len(users) == 1
            assert users[0].username == "alice"
            call_params = mock_kc.return_value.get_users.call_args[0][0]
            assert call_params.get("search") == "alice"
            assert call_params.get("max") == 5
            assert call_params.get("first") == 0
            assert call_params.get("enabled") == "true"


class TestKeycloakAdminAdapterCountUsers:
    """count_users(filters?)."""

    @pytest.mark.asyncio
    async def test_count_users_success(self, admin_config: KeycloakAdminConfig) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.users_count.return_value = 42
            adapter = KeycloakAdminAdapter(admin_config)
            count = await adapter.count_users()
            assert count == 42


# ═══════════════════════════════════════════════════════════════
# Password
# ═══════════════════════════════════════════════════════════════


class TestKeycloakAdminAdapterSetPassword:
    """set_password(user_id, password, temporary?)."""

    @pytest.mark.asyncio
    async def test_set_password_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.set_user_password.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.set_password("u99", "newpass")


class TestKeycloakAdminAdapterSendPasswordReset:
    """send_password_reset(user_id)."""

    @pytest.mark.asyncio
    async def test_send_password_reset_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.send_update_account.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.send_password_reset("u99")


class TestKeycloakAdminAdapterSendVerifyEmail:
    """send_verify_email(user_id)."""

    @pytest.mark.asyncio
    async def test_send_verify_email_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.send_verify_email.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.send_verify_email("u99")


# ═══════════════════════════════════════════════════════════════
# Roles
# ═══════════════════════════════════════════════════════════════


class TestKeycloakAdminAdapterListRoles:
    """list_roles()."""

    @pytest.mark.asyncio
    async def test_list_roles_success(self, admin_config: KeycloakAdminConfig) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_realm_roles.return_value = [
                {"id": "r1", "name": "user", "description": "User role"}
            ]
            adapter = KeycloakAdminAdapter(admin_config)
            roles = await adapter.list_roles()
            assert len(roles) == 1
            assert roles[0].name == "user"
            assert roles[0].role_id == "r1"


class TestKeycloakAdminAdapterGetUserRoles:
    """get_user_roles(user_id)."""

    @pytest.mark.asyncio
    async def test_get_user_roles_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_realm_roles_of_user.side_effect = KeycloakError(
                "404"
            )
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.get_user_roles("u99")


class TestKeycloakAdminAdapterAssignRoles:
    """assign_roles(user_id, role_names)."""

    @pytest.mark.asyncio
    async def test_assign_roles_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_realm_role.return_value = {
                "id": "r1",
                "name": "user",
            }
            mock_kc.return_value.assign_realm_roles.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.assign_roles("u99", ["user"])


class TestKeycloakAdminAdapterRemoveRoles:
    """remove_roles(user_id, role_names)."""

    @pytest.mark.asyncio
    async def test_remove_roles_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_realm_role.return_value = {
                "id": "r1",
                "name": "user",
            }
            mock_kc.return_value.delete_realm_roles_of_user.side_effect = KeycloakError(
                "404"
            )
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.remove_roles("u99", ["user"])


# ═══════════════════════════════════════════════════════════════
# Groups
# ═══════════════════════════════════════════════════════════════


class TestKeycloakAdminAdapterListGroups:
    """list_groups()."""

    @pytest.mark.asyncio
    async def test_list_groups_success(self, admin_config: KeycloakAdminConfig) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_groups.return_value = [
                {"id": "g1", "name": "mygroup", "path": "/mygroup"}
            ]
            adapter = KeycloakAdminAdapter(admin_config)
            groups = await adapter.list_groups()
            assert len(groups) == 1
            assert groups[0].group_id == "g1"
            assert groups[0].name == "mygroup"


class TestKeycloakAdminAdapterGetUserGroups:
    """get_user_groups(user_id)."""

    @pytest.mark.asyncio
    async def test_get_user_groups_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_user_groups.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.get_user_groups("u99")


class TestKeycloakAdminAdapterAddToGroups:
    """add_to_groups(user_id, group_ids)."""

    @pytest.mark.asyncio
    async def test_add_to_groups_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.group_user_add.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.add_to_groups("u99", ["g1"])


class TestKeycloakAdminAdapterRemoveFromGroups:
    """remove_from_groups(user_id, group_ids)."""

    @pytest.mark.asyncio
    async def test_remove_from_groups_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.group_user_remove.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.remove_from_groups("u99", ["g1"])


# ═══════════════════════════════════════════════════════════════
# Group roles
# ═══════════════════════════════════════════════════════════════


class TestKeycloakAdminAdapterGetGroupRoles:
    """get_group_roles(group_id)."""

    @pytest.mark.asyncio
    async def test_get_group_roles_success(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_group_realm_roles.return_value = [
                {"id": "r1", "name": "group-role"}
            ]
            adapter = KeycloakAdminAdapter(admin_config)
            roles = await adapter.get_group_roles("g1")
            assert len(roles) == 1
            assert roles[0].name == "group-role"


class TestKeycloakAdminAdapterAssignGroupRoles:
    """assign_group_roles(group_id, role_names)."""

    @pytest.mark.asyncio
    async def test_assign_group_roles_success(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_realm_role.return_value = {
                "id": "r1",
                "name": "user",
            }
            adapter = KeycloakAdminAdapter(admin_config)
            await adapter.assign_group_roles("g1", ["user"])
            mock_kc.return_value.assign_group_realm_roles.assert_called_once()


class TestKeycloakAdminAdapterRemoveGroupRoles:
    """remove_group_roles(group_id, role_names)."""

    @pytest.mark.asyncio
    async def test_remove_group_roles_success(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_realm_role.return_value = {
                "id": "r1",
                "name": "user",
            }
            adapter = KeycloakAdminAdapter(admin_config)
            await adapter.remove_group_roles("g1", ["user"])
            mock_kc.return_value.delete_group_realm_roles.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# Sessions
# ═══════════════════════════════════════════════════════════════


class TestKeycloakAdminAdapterGetUserSessions:
    """get_user_sessions(user_id)."""

    @pytest.mark.asyncio
    async def test_get_user_sessions_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.get_sessions.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.get_user_sessions("u99")


class TestKeycloakAdminAdapterLogoutUser:
    """logout_user(user_id)."""

    @pytest.mark.asyncio
    async def test_logout_user_404_raises_user_not_found_error(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            mock_kc.return_value.user_logout.side_effect = KeycloakError("404")
            adapter = KeycloakAdminAdapter(admin_config)
            with pytest.raises(UserNotFoundError):
                await adapter.logout_user("u99")


class TestKeycloakAdminAdapterRevokeUserSession:
    """revoke_user_session(session_id)."""

    @pytest.mark.asyncio
    async def test_revoke_user_session_success(
        self, admin_config: KeycloakAdminConfig
    ) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            adapter = KeycloakAdminAdapter(admin_config)
            await adapter.revoke_user_session("session-123")
            mock_kc.return_value.user_logout_all_session.assert_called_once_with(
                "session-123"
            )


# ═══════════════════════════════════════════════════════════════
# Mappers
# ═══════════════════════════════════════════════════════════════


class TestKeycloakAdminAdapterMappers:
    """_map_user, _map_role, _map_group."""

    def test_map_user(self, admin_config: KeycloakAdminConfig) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            adapter = KeycloakAdminAdapter(admin_config)
            kc_user = {
                "id": "u1",
                "username": "alice",
                "email": "a@b.com",
                "firstName": "Alice",
                "lastName": "U",
                "enabled": True,
                "emailVerified": True,
                "createdTimestamp": "123456",
            }
            user = adapter._map_user(kc_user)
            assert isinstance(user, UserData)
            assert user.user_id == "u1"
            assert user.username == "alice"
            assert user.first_name == "Alice"
            assert user.enabled is True

    def test_map_role(self, admin_config: KeycloakAdminConfig) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            adapter = KeycloakAdminAdapter(admin_config)
            kc_role = {
                "id": "r1",
                "name": "admin",
                "description": "Admin role",
                "composite": True,
            }
            role = adapter._map_role(kc_role)
            assert isinstance(role, RoleData)
            assert role.role_id == "r1"
            assert role.name == "admin"
            assert role.is_composite is True

    def test_map_group(self, admin_config: KeycloakAdminConfig) -> None:
        with patch("cqrs_ddd_identity.admin.keycloak.KeycloakAdmin") as mock_kc:
            mock_kc.return_value = MagicMock()
            adapter = KeycloakAdminAdapter(admin_config)
            kc_group = {
                "id": "g1",
                "name": "mygroup",
                "parentId": "g0",
                "path": "/parent/mygroup",
            }
            group = adapter._map_group(kc_group)
            assert isinstance(group, GroupData)
            assert group.group_id == "g1"
            assert group.name == "mygroup"
            assert group.parent_id == "g0"
            assert group.path == "/parent/mygroup"
