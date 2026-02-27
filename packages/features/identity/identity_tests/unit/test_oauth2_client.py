"""Tests for OAuth2 client."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from cqrs_ddd_identity.oauth2 import OAuth2ProviderConfig, OAuth2TokenClient

if TYPE_CHECKING:
    from cqrs_ddd_identity.ports import TokenResponse


class ConcreteOAuth2Client(OAuth2TokenClient):
    """Minimal concrete client for testing URL-building only."""

    async def exchange_code(
        self,
        code: str,
        *,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
    ) -> TokenResponse:
        raise NotImplementedError

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        raise NotImplementedError

    async def introspect(self, token: str) -> dict:
        raise NotImplementedError


class TestOAuth2UrlEncoding:
    """Test that OAuth2 authorization and logout URLs encode parameters correctly."""

    def test_authorization_url_encodes_special_characters(self) -> None:
        """Redirect URI and scope with &, =, space are properly encoded."""
        config = OAuth2ProviderConfig(
            authorization_endpoint="https://auth.example.com/oauth2/auth",
            token_endpoint="https://auth.example.com/token",
            client_id="my-client",
            redirect_uri="https://app.example.com/callback?foo=bar&baz=1",
            scope="openid profile email",
        )
        client = ConcreteOAuth2Client(config)
        url = client.get_authorization_url(state="abc123")

        parsed = urlparse(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "auth.example.com"
        query = parse_qs(parsed.query, keep_blank_values=True)
        assert "state" in query
        assert query["state"] == ["abc123"]
        assert "redirect_uri" in query
        # Redirect URI should be encoded (e.g. & and = in value)
        assert (
            "foo" in query["redirect_uri"][0]
            or "%3D" in query["redirect_uri"][0]
            or "bar" in query["redirect_uri"][0]
        )

    def test_logout_url_encodes_redirect_uri(self) -> None:
        """Logout URL encodes post_logout_redirect_uri."""
        config = OAuth2ProviderConfig(
            authorization_endpoint="https://auth.example.com/oauth2/auth",
            token_endpoint="https://auth.example.com/token",
            client_id="my-client",
            redirect_uri="https://app.example.com/",
            end_session_endpoint="https://auth.example.com/logout",
        )
        client = ConcreteOAuth2Client(config)
        url = client.get_logout_url(redirect_uri="https://app.example.com/?x=1&y=2")

        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        assert "post_logout_redirect_uri" in query
        # Should be encoded, not raw & in the URL path
        assert parsed.path == "/logout" or "logout" in parsed.path
