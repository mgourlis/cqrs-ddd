"""Integration tests for Keycloak OAuth2 identity provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from cqrs_ddd_identity.oauth2 import KeycloakIdentityProvider


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_authenticate_success(
    keycloak_identity_provider: KeycloakIdentityProvider,
):
    """Test successful authentication with valid credentials."""
    # Authenticate using master realm admin (returns TokenResponse)
    tokens = await keycloak_identity_provider.authenticate(
        username="admin",
        password="admin123",
    )

    assert tokens is not None
    assert tokens.access_token is not None
    assert tokens.refresh_token is not None
    # Resolve token to Principal
    principal = await keycloak_identity_provider.resolve(token=tokens.access_token)
    assert principal is not None
    assert principal.username == "admin"
    assert principal.user_id is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_authenticate_failure(
    keycloak_identity_provider: KeycloakIdentityProvider,
):
    """Test authentication failure with invalid credentials."""
    with pytest.raises(Exception):  # KeycloakError or similar
        await keycloak_identity_provider.authenticate(
            username="admin",
            password="wrongpassword",
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_get_user_info(
    keycloak_identity_provider: KeycloakIdentityProvider,
):
    """Test retrieving user information."""
    # First authenticate to get a token
    tokens = await keycloak_identity_provider.authenticate(
        username="admin",
        password="admin123",
    )

    # get_user_info returns a dict from Keycloak userinfo endpoint
    user_info = await keycloak_identity_provider.get_user_info(tokens.access_token)

    assert user_info is not None
    assert user_info.get("preferred_username") == "admin"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_refresh_token(
    keycloak_identity_provider: KeycloakIdentityProvider,
):
    """Test token refresh."""
    # First authenticate (returns TokenResponse)
    tokens = await keycloak_identity_provider.authenticate(
        username="admin",
        password="admin123",
    )

    old_token = tokens.access_token
    assert tokens.refresh_token is not None

    # refresh() returns TokenResponse
    refreshed = await keycloak_identity_provider.refresh(
        refresh_token=tokens.refresh_token,
    )

    assert refreshed is not None
    assert refreshed.access_token != old_token
    assert refreshed.refresh_token is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_logout(
    keycloak_identity_provider: KeycloakIdentityProvider,
):
    """Test user logout."""
    # First authenticate
    tokens = await keycloak_identity_provider.authenticate(
        username="admin",
        password="admin123",
    )
    assert tokens.refresh_token is not None

    # logout(token) takes the refresh token to invalidate
    await keycloak_identity_provider.logout(tokens.refresh_token)

    # The refresh token should now be invalid; refresh should fail
    with pytest.raises(Exception):
        await keycloak_identity_provider.refresh(
            refresh_token=tokens.refresh_token,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_resolve_token(
    keycloak_identity_provider: KeycloakIdentityProvider,
):
    """Test resolving a JWT token to a Principal."""
    # Authenticate to get tokens (TokenResponse)
    tokens = await keycloak_identity_provider.authenticate(
        username="admin",
        password="admin123",
    )

    # Resolve the access token to a Principal
    resolved = await keycloak_identity_provider.resolve(token=tokens.access_token)

    assert resolved is not None
    assert resolved.username == "admin"
    assert resolved.user_id is not None
    # Realm roles appear in token only when client scope mappers include them
    if resolved.roles:
        assert "admin" in resolved.roles or "uma_authorization" in resolved.roles


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_clear_key_cache(
    keycloak_identity_provider: KeycloakIdentityProvider,
):
    """Test that clearing the key cache re-fetches the public key and resolve still works."""
    tokens = await keycloak_identity_provider.authenticate(
        username="admin",
        password="admin123",
    )
    access_token = tokens.access_token

    principal_before = await keycloak_identity_provider.resolve(token=access_token)
    assert principal_before is not None
    assert principal_before.username == "admin"
    assert principal_before.user_id is not None

    keycloak_identity_provider.clear_key_cache()
    principal_after = await keycloak_identity_provider.resolve(token=access_token)

    assert principal_after is not None
    assert principal_after.user_id == principal_before.user_id
    assert principal_after.username == principal_before.username
