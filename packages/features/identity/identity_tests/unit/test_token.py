"""Tests for token extraction and API key utilities."""

from __future__ import annotations

import hashlib
import re

from cqrs_ddd_identity.token import (
    TokenExtractor,
    TokenSource,
    extract_api_key,
    extract_bearer_token,
    extract_token,
    generate_api_key,
    get_api_key_prefix,
    hash_api_key,
)


class TestExtractBearerToken:
    """Test extract_bearer_token."""

    def test_returns_none_when_no_authorization_header(self) -> None:
        assert extract_bearer_token({}) is None
        assert extract_bearer_token({"Content-Type": "application/json"}) is None

    def test_returns_none_when_header_lowercase_no_bearer(self) -> None:
        assert extract_bearer_token({"authorization": "Basic xyz"}) is None

    def test_returns_none_when_single_part(self) -> None:
        assert extract_bearer_token({"Authorization": "BearerOnly"}) is None

    def test_returns_none_when_three_parts(self) -> None:
        assert extract_bearer_token({"Authorization": "Bearer tok extra"}) is None

    def test_returns_none_when_scheme_not_bearer(self) -> None:
        assert extract_bearer_token({"Authorization": "Basic dG9r"}) is None
        assert extract_bearer_token({"Authorization": "ApiKey sk-abc"}) is None

    def test_returns_token_when_bearer(self) -> None:
        assert extract_bearer_token({"Authorization": "Bearer jwt.here"}) == "jwt.here"
        assert extract_bearer_token({"authorization": "Bearer jwt.here"}) == "jwt.here"
        assert extract_bearer_token({"Authorization": "BEARER x"}) == "x"


class TestExtractApiKey:
    """Test extract_api_key."""

    def test_returns_none_when_no_headers(self) -> None:
        assert extract_api_key({}) is None

    def test_returns_from_x_api_key_header(self) -> None:
        assert extract_api_key({"X-API-Key": "sk-abc123"}) == "sk-abc123"
        assert extract_api_key({"x-api-key": "sk-xyz"}) == "sk-xyz"

    def test_returns_from_authorization_apikey(self) -> None:
        assert extract_api_key({"Authorization": "ApiKey sk-key"}) == "sk-key"
        assert extract_api_key({"authorization": "apikey sk-key"}) == "sk-key"

    def test_returns_none_when_authorization_not_apikey(self) -> None:
        assert extract_api_key({"Authorization": "Bearer x"}) is None
        assert extract_api_key({"Authorization": "Basic x"}) is None

    def test_returns_none_when_authorization_malformed(self) -> None:
        assert extract_api_key({"Authorization": "ApiKey"}) is None
        assert extract_api_key({"Authorization": "ApiKey a b"}) is None

    def test_x_api_key_takes_precedence_over_authorization(self) -> None:
        # When both present, X-API-Key is tried first in extract_token flow;
        # extract_api_key itself returns first found (X-API-Key)
        assert (
            extract_api_key({"X-API-Key": "first", "Authorization": "ApiKey second"})
            == "first"
        )


class TestExtractToken:
    """Test extract_token priority order."""

    def test_bearer_takes_priority(self) -> None:
        headers = {"Authorization": "Bearer jwt", "X-API-Key": "sk-x"}
        cookies = {"access_token": "cookie-tok"}
        params = {"access_token": "query-tok"}
        token, source = extract_token(headers, cookies, params)
        assert token == "jwt"
        assert source == TokenSource.HEADER

    def test_api_key_second(self) -> None:
        headers = {"X-API-Key": "sk-abc"}
        cookies = {"access_token": "cookie-tok"}
        params = {"access_token": "query-tok"}
        token, source = extract_token(headers, cookies, params)
        assert token == "sk-abc"
        assert source == TokenSource.API_KEY

    def test_cookie_third(self) -> None:
        headers = {}
        cookies = {"access_token": "cookie-tok"}
        params = {"access_token": "query-tok"}
        token, source = extract_token(headers, cookies, params)
        assert token == "cookie-tok"
        assert source == TokenSource.COOKIE

    def test_query_fourth(self) -> None:
        headers = {}
        cookies = {}
        params = {"access_token": "query-tok"}
        token, source = extract_token(headers, cookies, params)
        assert token == "query-tok"
        assert source == TokenSource.QUERY

    def test_none_when_empty(self) -> None:
        token, source = extract_token({}, None, None)
        assert token is None
        assert source is None

    def test_none_when_cookies_none(self) -> None:
        token, source = extract_token({}, None, {"access_token": "q"})
        assert token == "q"
        assert source == TokenSource.QUERY


class TestHashApiKey:
    """Test hash_api_key."""

    def test_returns_sha256_hex(self) -> None:
        result = hash_api_key("sk-secret")
        expected = hashlib.sha256(b"sk-secret").hexdigest()
        assert result == expected

    def test_deterministic(self) -> None:
        assert hash_api_key("key") == hash_api_key("key")


class TestGenerateApiKey:
    """Test generate_api_key."""

    def test_default_prefix_sk(self) -> None:
        key = generate_api_key()
        assert key.startswith("sk_")
        assert len(key) > 10

    def test_custom_prefix(self) -> None:
        key = generate_api_key(prefix="pk")
        assert key.startswith("pk_")

    def test_urlsafe_chars(self) -> None:
        key = generate_api_key(prefix="x")
        # After "x_" should be url-safe base64 chars
        rest = key[2:]
        assert re.match(r"^[A-Za-z0-9_-]+$", rest)


class TestGetApiKeyPrefix:
    """Test get_api_key_prefix."""

    def test_returns_first_8_chars(self) -> None:
        assert get_api_key_prefix("sk_abcdefghijklmnop") == "sk_abcde"  # 8 chars

    def test_short_key_returns_full(self) -> None:
        assert get_api_key_prefix("short") == "short"


class TestTokenExtractor:
    """Test TokenExtractor."""

    def test_bearer_first(self) -> None:
        ext = TokenExtractor()
        token, source = ext.extract(
            {"Authorization": "Bearer jwt"},
            {"access_token": "cookie"},
            {"access_token": "query"},
        )
        assert token == "jwt"
        assert source == TokenSource.HEADER

    def test_api_key_when_allowed(self) -> None:
        ext = TokenExtractor(allow_api_key=True)
        token, source = ext.extract({"X-API-Key": "sk-x"}, None, None)
        assert token == "sk-x"
        assert source == TokenSource.API_KEY

    def test_api_key_disabled_returns_none_for_api_key_header(self) -> None:
        ext = TokenExtractor(allow_api_key=False)
        token, source = ext.extract({"X-API-Key": "sk-x"}, None, None)
        assert token is None
        assert source is None

    def test_cookie_with_custom_name(self) -> None:
        ext = TokenExtractor(cookie_name="session_token")
        token, source = ext.extract({}, {"session_token": "sess-123"}, None)
        assert token == "sess-123"
        assert source == TokenSource.COOKIE

    def test_cookie_disabled_ignores_cookie(self) -> None:
        ext = TokenExtractor(allow_cookies=False)
        token, source = ext.extract({}, {"access_token": "c"}, None)
        assert token is None
        assert source is None

    def test_query_param_when_allowed(self) -> None:
        ext = TokenExtractor(allow_query_params=True)
        token, source = ext.extract({}, None, {"access_token": "q"})
        assert token == "q"
        assert source == TokenSource.QUERY

    def test_query_param_custom_name(self) -> None:
        ext = TokenExtractor(allow_query_params=True, query_param_name="token")
        token, source = ext.extract({}, None, {"token": "t"})
        assert token == "t"
        assert source == TokenSource.QUERY

    def test_query_disabled_ignores_query(self) -> None:
        ext = TokenExtractor(allow_query_params=False)
        token, source = ext.extract({}, None, {"access_token": "q"})
        assert token is None
        assert source is None
