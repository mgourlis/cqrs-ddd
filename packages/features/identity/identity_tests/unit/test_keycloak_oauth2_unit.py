"""Unit tests for Keycloak OAuth2 identity provider (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cqrs_ddd_identity.exceptions import AuthenticationError, InvalidTokenError
from cqrs_ddd_identity.oauth2.keycloak import (
    GroupPathStrategy,
    KeycloakConfig,
    KeycloakIdentityProvider,
)
from cqrs_ddd_identity.ports import TokenResponse

# ═══════════════════════════════════════════════════════════════
# KeycloakConfig
# ═══════════════════════════════════════════════════════════════


class TestKeycloakConfig:
    """KeycloakConfig dataclass."""

    def test_construction_defaults(self) -> None:
        config = KeycloakConfig(
            server_url="https://kc.example.com",
            realm="my-realm",
            client_id="my-client",
        )
        assert config.server_url == "https://kc.example.com"
        assert config.realm == "my-realm"
        assert config.client_id == "my-client"
        assert config.client_secret is None
        assert config.username_claim == "preferred_username"
        assert config.merge_groups_as_roles is True
        assert config.group_path_strategy == GroupPathStrategy.FULL_PATH
        assert config.group_prefix == ""


# ═══════════════════════════════════════════════════════════════
# GroupPathStrategy
# ═══════════════════════════════════════════════════════════════


class TestGroupPathStrategy:
    """GroupPathStrategy enum."""

    def test_enum_values(self) -> None:
        assert GroupPathStrategy.FULL_PATH.value == "full_path"
        assert GroupPathStrategy.LAST_SEGMENT.value == "last_segment"
        assert GroupPathStrategy.ALL_SEGMENTS.value == "all_segments"


# ═══════════════════════════════════════════════════════════════
# KeycloakIdentityProvider
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def keycloak_config() -> KeycloakConfig:
    return KeycloakConfig(
        server_url="https://kc.example.com",
        realm="test-realm",
        client_id="test-client",
        client_secret="secret",
    )


class TestKeycloakIdentityProviderInit:
    """Provider __init__ and client creation."""

    def test_init_creates_keycloak_openid(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc:
            mock_kc.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            assert provider.config is keycloak_config
            mock_kc.assert_called_once()
            call_kw = mock_kc.call_args[1]
            assert call_kw["server_url"] == keycloak_config.server_url
            assert call_kw["realm_name"] == keycloak_config.realm
            assert call_kw["client_id"] == keycloak_config.client_id
            assert call_kw["client_secret_key"] == keycloak_config.client_secret


class TestKeycloakIdentityProviderAuthenticate:
    """authenticate(username, password)."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.token.return_value = {
                "access_token": "at",
                "refresh_token": "rt",
                "token_type": "Bearer",
                "expires_in": 300,
                "scope": "openid",
            }
            mock_kc_cls.return_value = mock_kc

            provider = KeycloakIdentityProvider(keycloak_config)
            result = await provider.authenticate("user", "pass")

            assert isinstance(result, TokenResponse)
            assert result.access_token == "at"
            assert result.refresh_token == "rt"
            assert result.token_type == "Bearer"
            assert result.expires_in == 300
            mock_kc.token.assert_called_once_with("user", "pass")

    @pytest.mark.asyncio
    async def test_authenticate_raises_authentication_error(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.token.side_effect = Exception("Invalid credentials")
            mock_kc_cls.return_value = mock_kc

            provider = KeycloakIdentityProvider(keycloak_config)
            with pytest.raises(AuthenticationError, match="Invalid credentials"):
                await provider.authenticate("user", "wrong")


class TestKeycloakIdentityProviderResolve:
    """resolve(token)."""

    @pytest.mark.asyncio
    async def test_resolve_success_returns_principal(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)

            payload = {
                "sub": "user-123",
                "preferred_username": "alice",
                "realm_access": {"roles": ["user", "admin"]},
                "exp": 9999999999,  # joserfc JWTClaimsRegistry requires exp
            }
            # joserfc decode returns a token object with .claims
            decoded = MagicMock()
            decoded.claims = payload
            with (
                patch(
                    "cqrs_ddd_identity.oauth2.keycloak.jwt.decode", return_value=decoded
                ),
                patch.object(provider, "_get_public_key", return_value=MagicMock()),
            ):
                principal = await provider.resolve("fake-jwt")

            assert principal.user_id == "user-123"
            assert principal.username == "alice"
            assert "user" in principal.roles
            assert "admin" in principal.roles
            assert principal.auth_method == "oauth2"

    @pytest.mark.asyncio
    async def test_resolve_jwt_error_raises_invalid_token_error(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        from joserfc.errors import DecodeError

        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            with (
                patch.object(provider, "_get_public_key", return_value=MagicMock()),
                patch(
                    "cqrs_ddd_identity.oauth2.keycloak.jwt.decode",
                    side_effect=DecodeError("expired"),
                ),
                pytest.raises(InvalidTokenError, match="expired"),
            ):
                await provider.resolve("bad-token")


class TestKeycloakIdentityProviderRefresh:
    """refresh(refresh_token)."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.refresh_token.return_value = {
                "access_token": "new-at",
                "refresh_token": "new-rt",
                "expires_in": 3600,
            }
            mock_kc_cls.return_value = mock_kc

            provider = KeycloakIdentityProvider(keycloak_config)
            result = await provider.refresh("old-rt")

            assert result.access_token == "new-at"
            assert result.refresh_token == "new-rt"
            mock_kc.refresh_token.assert_called_once_with("old-rt")

    @pytest.mark.asyncio
    async def test_refresh_raises_authentication_error(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.refresh_token.side_effect = Exception("Token expired")
            mock_kc_cls.return_value = mock_kc

            provider = KeycloakIdentityProvider(keycloak_config)
            with pytest.raises(AuthenticationError, match="Token expired"):
                await provider.refresh("invalid-rt")


class TestKeycloakIdentityProviderLogout:
    """logout(token)."""

    @pytest.mark.asyncio
    async def test_logout_calls_keycloak_logout(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc_cls.return_value = mock_kc

            provider = KeycloakIdentityProvider(keycloak_config)
            await provider.logout("refresh-token")

            mock_kc.logout.assert_called_once_with("refresh-token")

    @pytest.mark.asyncio
    async def test_logout_swallows_exception(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.logout.side_effect = Exception("Network error")
            mock_kc_cls.return_value = mock_kc

            provider = KeycloakIdentityProvider(keycloak_config)
            await provider.logout("rt")  # no raise


class TestKeycloakIdentityProviderGetUserInfo:
    """get_user_info(access_token)."""

    @pytest.mark.asyncio
    async def test_get_user_info_success(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.userinfo.return_value = {
                "preferred_username": "alice",
                "email": "alice@example.com",
            }
            mock_kc_cls.return_value = mock_kc

            provider = KeycloakIdentityProvider(keycloak_config)
            result = await provider.get_user_info("at")

            assert result["preferred_username"] == "alice"
            assert result["email"] == "alice@example.com"
            mock_kc.userinfo.assert_called_once_with("at")

    @pytest.mark.asyncio
    async def test_get_user_info_raises_invalid_token_error(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.userinfo.side_effect = Exception("Invalid token")
            mock_kc_cls.return_value = mock_kc

            provider = KeycloakIdentityProvider(keycloak_config)
            with pytest.raises(InvalidTokenError, match="Invalid token"):
                await provider.get_user_info("bad-at")


class TestKeycloakIdentityProviderGetPublicKey:
    """_get_public_key() caching and None handling."""

    def test_get_public_key_caches(self, keycloak_config: KeycloakConfig) -> None:
        fake_jwk = MagicMock()
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.public_key.return_value = "raw-key-content"
            mock_kc_cls.return_value = mock_kc
            with patch(
                "cqrs_ddd_identity.oauth2.keycloak.import_key",
                return_value=fake_jwk,
            ):
                provider = KeycloakIdentityProvider(keycloak_config)
                key1 = provider._get_public_key()
                key2 = provider._get_public_key()

            assert key1 is key2
            assert key1 is fake_jwk
            mock_kc.public_key.assert_called_once()

    def test_get_public_key_none_raises_invalid_token_error(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.public_key.return_value = None
            mock_kc_cls.return_value = mock_kc

            provider = KeycloakIdentityProvider(keycloak_config)
            with pytest.raises(InvalidTokenError, match="Failed to retrieve"):
                provider._get_public_key()


class TestKeycloakIdentityProviderPayloadToPrincipal:
    """_payload_to_principal(payload) with various payloads."""

    def test_realm_access_roles(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            payload = {
                "sub": "u1",
                "preferred_username": "bob",
                "realm_access": {"roles": ["realm-role"]},
            }
            principal = provider._payload_to_principal(payload)
            assert principal.user_id == "u1"
            assert principal.username == "bob"
            assert "realm-role" in principal.roles

    def test_resource_access_roles_same_client(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            payload = {
                "sub": "u1",
                "preferred_username": "bob",
                "resource_access": {
                    keycloak_config.client_id: {"roles": ["client-role"]},
                },
            }
            principal = provider._payload_to_principal(payload)
            assert "client-role" in principal.roles

    def test_resource_access_roles_other_client_prefixed(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            payload = {
                "sub": "u1",
                "preferred_username": "bob",
                "resource_access": {"other-client": {"roles": ["role1"]}},
            }
            principal = provider._payload_to_principal(payload)
            assert "other-client:role1" in principal.roles

    def test_groups_merged_as_roles(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            payload = {
                "sub": "u1",
                "preferred_username": "bob",
                "groups": ["/web/admin"],
            }
            principal = provider._payload_to_principal(payload)
            assert "web/admin" in principal.roles

    def test_tenant_id_claim_and_use_realm(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            config = KeycloakConfig(
                server_url="https://k",
                realm="my-realm",
                client_id="c",
                use_realm_as_tenant=True,
            )
            provider = KeycloakIdentityProvider(config)
            payload = {"sub": "u1", "preferred_username": "bob"}
            principal = provider._payload_to_principal(payload)
            assert principal.tenant_id == "my-realm"

    def test_username_fallback_email_then_sub(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            config = KeycloakConfig(
                server_url="https://k",
                realm="r",
                client_id="c",
                username_claim="email",
            )
            provider = KeycloakIdentityProvider(config)
            payload = {"sub": "u1", "email": "user@example.com"}
            principal = provider._payload_to_principal(payload)
            assert principal.username == "user@example.com"

    def test_mfa_verified_from_acr(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            payload = {"sub": "u1", "preferred_username": "bob", "acr": "mfa"}
            principal = provider._payload_to_principal(payload)
            assert principal.mfa_verified is True


class TestKeycloakIdentityProviderGroupPathToRoles:
    """_group_path_to_roles(group_path, strategy, prefix)."""

    def test_full_path(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            roles = provider._group_path_to_roles(
                "/web/admin/editor",
                GroupPathStrategy.FULL_PATH,
                "",
            )
            assert roles == {"web/admin/editor"}

    def test_full_path_with_prefix(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            roles = provider._group_path_to_roles(
                "/web/admin",
                GroupPathStrategy.FULL_PATH,
                "grp:",
            )
            assert roles == {"grp:web/admin"}

    def test_last_segment(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            roles = provider._group_path_to_roles(
                "/web/admin/editor",
                GroupPathStrategy.LAST_SEGMENT,
                "",
            )
            assert roles == {"editor"}

    def test_all_segments(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            roles = provider._group_path_to_roles(
                "/web/admin/editor",
                GroupPathStrategy.ALL_SEGMENTS,
                "",
            )
            assert roles == {"web", "admin", "editor"}

    def test_empty_path_returns_empty_set(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            roles = provider._group_path_to_roles(
                "/",
                GroupPathStrategy.FULL_PATH,
                "",
            )
            assert roles == set()


class TestKeycloakIdentityProviderClearKeyCache:
    """clear_key_cache()."""

    def test_clear_key_cache_forces_refetch(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc = MagicMock()
            mock_kc.public_key.return_value = "key1"
            mock_kc_cls.return_value = mock_kc
            with patch(
                "cqrs_ddd_identity.oauth2.keycloak.import_key",
                return_value=MagicMock(),
            ):
                provider = KeycloakIdentityProvider(keycloak_config)
                provider._get_public_key()
                assert mock_kc.public_key.call_count == 1
                provider.clear_key_cache()
                assert provider._public_key_pem is None
                assert provider._public_key_jwk is None
                provider._get_public_key()
                assert mock_kc.public_key.call_count == 2


class TestKeycloakIdentityProviderRequiresOtp:
    """requires_otp(claims)."""

    def test_requires_otp_acr_mfa(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            assert provider.requires_otp({"acr": "mfa"}) is True

    def test_requires_otp_otp_required_true(
        self, keycloak_config: KeycloakConfig
    ) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            assert provider.requires_otp({"otp_required": True}) is True

    def test_requires_otp_false(self, keycloak_config: KeycloakConfig) -> None:
        with patch("cqrs_ddd_identity.oauth2.keycloak.KeycloakOpenID") as mock_kc_cls:
            mock_kc_cls.return_value = MagicMock()
            provider = KeycloakIdentityProvider(keycloak_config)
            assert provider.requires_otp({"acr": "0"}) is False
            assert provider.requires_otp({}) is False
