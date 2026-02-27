"""Tests for OAuth2 state management."""

from __future__ import annotations

import pytest

from cqrs_ddd_identity.oauth2.state import (
    OAuthStateData,
    OAuthStateManager,
    generate_oauth_state,
)
from cqrs_ddd_identity.session import InMemorySessionStore


class TestOAuthStateData:
    """Test OAuthStateData."""

    def test_created_at_set_by_default(self) -> None:
        data = OAuthStateData(state="abc")
        assert data.created_at is not None

    def test_to_dict(self) -> None:
        data = OAuthStateData(
            state="s1",
            pkce_verifier="v1",
            redirect_uri="/cb",
            provider="keycloak",
        )
        d = data.to_dict()
        assert d["state"] == "s1"
        assert d["pkce_verifier"] == "v1"
        assert d["redirect_uri"] == "/cb"
        assert d["provider"] == "keycloak"
        assert "created_at" in d

    def test_from_dict(self) -> None:
        d = {
            "state": "s1",
            "pkce_verifier": "v1",
            "redirect_uri": "/cb",
        }
        data = OAuthStateData.from_dict(d)
        assert data.state == "s1"
        assert data.pkce_verifier == "v1"
        assert data.redirect_uri == "/cb"

    def test_from_dict_missing_state_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing required 'state'"):
            OAuthStateData.from_dict({})

    def test_from_dict_with_timestamp_string(self) -> None:
        d = {"state": "s1", "created_at": "2024-01-15T12:00:00+00:00"}
        data = OAuthStateData.from_dict(d)
        assert data.state == "s1"
        assert data.created_at is not None


class TestGenerateOAuthState:
    def test_returns_string(self) -> None:
        s = generate_oauth_state()
        assert isinstance(s, str)
        assert len(s) > 0

    def test_custom_length(self) -> None:
        s = generate_oauth_state(length=16)
        assert isinstance(s, str)


class TestOAuthStateManager:
    @pytest.fixture
    def session_store(self) -> InMemorySessionStore:
        return InMemorySessionStore()

    @pytest.fixture
    def manager(self, session_store: InMemorySessionStore) -> OAuthStateManager:
        return OAuthStateManager(session_store)

    def test_create_state(self, manager: OAuthStateManager) -> None:
        data = manager.create_state(
            provider="keycloak",
            pkce_verifier="verifier-123",
            redirect_uri="/auth/callback",
        )
        assert data.state is not None
        assert data.provider == "keycloak"
        assert data.pkce_verifier == "verifier-123"
        assert data.redirect_uri == "/auth/callback"

    @pytest.mark.asyncio
    async def test_store_and_get_state(
        self, manager: OAuthStateManager, session_store: InMemorySessionStore
    ) -> None:
        data = manager.create_state(provider="k1")
        await manager.store_state(data)
        retrieved = await manager.get_state(data.state)
        assert retrieved is not None
        assert retrieved.state == data.state
        assert retrieved.provider == data.provider

    @pytest.mark.asyncio
    async def test_get_state_missing_returns_none(
        self, manager: OAuthStateManager
    ) -> None:
        assert await manager.get_state("nonexistent") is None

    @pytest.mark.asyncio
    async def test_validate_state_consumes_state(
        self, manager: OAuthStateManager
    ) -> None:
        data = manager.create_state(provider="k1")
        await manager.store_state(data)
        validated = await manager.validate_state(data.state)
        assert validated is not None
        assert validated.state == data.state
        assert await manager.get_state(data.state) is None

    @pytest.mark.asyncio
    async def test_delete_state(self, manager: OAuthStateManager) -> None:
        data = manager.create_state(provider="k1")
        await manager.store_state(data)
        await manager.delete_state(data.state)
        assert await manager.get_state(data.state) is None
