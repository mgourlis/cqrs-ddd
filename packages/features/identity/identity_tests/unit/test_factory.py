"""Tests for CompositeIdentityProvider and factory functions."""

from __future__ import annotations

import pytest

from cqrs_ddd_identity import Principal
from cqrs_ddd_identity.exceptions import AuthenticationError, InvalidTokenError
from cqrs_ddd_identity.factory import (
    CompositeIdentityProvider,
    create_api_only_provider,
    create_composite_provider,
    create_hybrid_provider,
)
from cqrs_ddd_identity.ports import TokenResponse


class MockProviderSucceeds:
    """Mock provider that resolves to a principal."""

    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def resolve(self, token: str) -> Principal:
        return self.principal

    async def refresh(self, refresh_token: str) -> TokenResponse:
        return TokenResponse(access_token="new_access", refresh_token="new_refresh")

    async def logout(self, token: str) -> None:
        pass


class MockProviderInvalidToken:
    """Mock provider that raises InvalidTokenError."""

    async def resolve(self, token: str) -> Principal:
        raise InvalidTokenError("Unknown token")

    async def refresh(self, refresh_token: str) -> TokenResponse:
        raise InvalidTokenError("Unknown refresh")

    async def logout(self, token: str) -> None:
        pass


class MockProviderAuthError:
    """Mock provider that raises AuthenticationError."""

    async def resolve(self, token: str) -> Principal:
        raise AuthenticationError("Auth failed")

    async def refresh(self, refresh_token: str) -> TokenResponse:
        raise AuthenticationError("Refresh failed")

    async def logout(self, token: str) -> None:
        raise RuntimeError("logout failed")


@pytest.fixture
def principal() -> Principal:
    return Principal(
        user_id="u1", username="user1", roles=frozenset(), permissions=frozenset()
    )


class TestCompositeIdentityProvider:
    """Test CompositeIdentityProvider."""

    @pytest.mark.asyncio
    async def test_resolve_first_provider_succeeds(self, principal: Principal) -> None:
        p1 = MockProviderSucceeds(principal)
        p2 = MockProviderInvalidToken()
        composite = CompositeIdentityProvider([p1, p2])
        result = await composite.resolve("any-token")
        assert result == principal

    @pytest.mark.asyncio
    async def test_resolve_second_provider_succeeds_on_invalid_token(
        self, principal: Principal
    ) -> None:
        p1 = MockProviderInvalidToken()
        p2 = MockProviderSucceeds(principal)
        composite = CompositeIdentityProvider([p1, p2])
        result = await composite.resolve("any-token")
        assert result == principal

    @pytest.mark.asyncio
    async def test_resolve_authentication_error_re_raised(
        self, principal: Principal
    ) -> None:
        p1 = MockProviderAuthError()
        p2 = MockProviderSucceeds(principal)
        composite = CompositeIdentityProvider([p1, p2])
        with pytest.raises(AuthenticationError, match="Auth failed"):
            await composite.resolve("token")

    @pytest.mark.asyncio
    async def test_resolve_all_invalid_raises_last_error(self) -> None:
        composite = CompositeIdentityProvider(
            [MockProviderInvalidToken(), MockProviderInvalidToken()]
        )
        with pytest.raises(InvalidTokenError, match="Unknown token"):
            await composite.resolve("token")

    @pytest.mark.asyncio
    async def test_empty_providers_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="At least one provider is required"):
            CompositeIdentityProvider([])

    @pytest.mark.asyncio
    async def test_refresh_uses_first_provider(self, principal: Principal) -> None:
        p1 = MockProviderSucceeds(principal)
        composite = CompositeIdentityProvider([p1])
        resp = await composite.refresh("refresh-tok")
        assert resp.access_token == "new_access"
        assert resp.refresh_token == "new_refresh"

    @pytest.mark.asyncio
    async def test_logout_calls_all_providers(self, principal: Principal) -> None:
        p1 = MockProviderSucceeds(principal)
        p2 = MockProviderSucceeds(principal)
        composite = CompositeIdentityProvider([p1, p2])
        await composite.logout("token")

    @pytest.mark.asyncio
    async def test_logout_raises_when_all_fail(self) -> None:
        composite = CompositeIdentityProvider(
            [MockProviderAuthError(), MockProviderAuthError()]
        )
        with pytest.raises(RuntimeError, match="logout failed"):
            await composite.logout("token")

    def test_providers_property(self, principal: Principal) -> None:
        p1 = MockProviderSucceeds(principal)
        p2 = MockProviderInvalidToken()
        composite = CompositeIdentityProvider([p1, p2])
        assert composite.providers == [p1, p2]


class TestCreateCompositeProvider:
    """Test create_composite_provider."""

    def test_returns_composite(self, principal: Principal) -> None:
        p1 = MockProviderSucceeds(principal)
        provider = create_composite_provider(p1)
        assert isinstance(provider, CompositeIdentityProvider)
        assert provider.providers == [p1]

    def test_multiple_providers(self, principal: Principal) -> None:
        p1 = MockProviderSucceeds(principal)
        p2 = MockProviderInvalidToken()
        provider = create_composite_provider(p1, p2)
        assert len(provider.providers) == 2


class TestCreateHybridProvider:
    """Test create_hybrid_provider."""

    def test_returns_composite_with_primary_and_fallback(
        self, principal: Principal
    ) -> None:
        primary = MockProviderSucceeds(principal)
        fallback = MockProviderInvalidToken()
        provider = create_hybrid_provider(primary=primary, fallback=fallback)
        assert isinstance(provider, CompositeIdentityProvider)
        assert provider.providers == [primary, fallback]


class TestCreateApiOnlyProvider:
    """Test create_api_only_provider."""

    def test_returns_same_provider(self, principal: Principal) -> None:
        p = MockProviderSucceeds(principal)
        result = create_api_only_provider(p)
        assert result is p
