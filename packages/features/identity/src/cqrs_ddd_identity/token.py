"""Token validation and extraction utilities.

Provides JWT token validation, signature verification, and extraction
of bearer tokens from HTTP headers.
"""

from __future__ import annotations

import hashlib
import secrets
from enum import Enum


class TokenSource(str, Enum):
    """Source from which token was extracted."""

    HEADER = "header"  # Authorization: Bearer <token>
    COOKIE = "cookie"  # access_token cookie
    API_KEY = "api_key"  # X-API-Key header
    QUERY = "query"  # ?access_token=<token>


def extract_bearer_token(headers: dict[str, str]) -> str | None:
    """Extract Bearer token from Authorization header.

    Args:
        headers: HTTP headers dictionary.

    Returns:
        Token string or None if not found.

    Example:
        ```python
        token = extract_bearer_token(request.headers)
        if token:
            principal = await provider.resolve(token)
        ```
    """
    auth_header = headers.get("Authorization") or headers.get("authorization")
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2:
        return None

    scheme, token = parts
    if scheme.lower() != "bearer":
        return None

    return token


def extract_api_key(headers: dict[str, str]) -> str | None:
    """Extract API key from X-API-Key header.

    Also supports Authorization: ApiKey <key> format.

    Args:
        headers: HTTP headers dictionary.

    Returns:
        API key string or None if not found.

    Example:
        ```python
        api_key = extract_api_key(request.headers)
        if api_key:
            principal = await api_key_provider.resolve(api_key)
        ```
    """
    # Try X-API-Key header first
    api_key = headers.get("X-API-Key") or headers.get("x-api-key")
    if api_key:
        return api_key

    # Try Authorization: ApiKey <key>
    auth_header = headers.get("Authorization") or headers.get("authorization")
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2:
        return None

    scheme, key = parts
    if scheme.lower() != "apikey":
        return None

    return key


def extract_token(
    headers: dict[str, str],
    cookies: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
) -> tuple[str | None, TokenSource | None]:
    """Extract token from multiple sources with priority order.

    Priority order:
    1. Authorization: Bearer header
    2. X-API-Key header
    3. access_token cookie
    4. access_token query parameter

    Args:
        headers: HTTP headers dictionary.
        cookies: Optional cookies dictionary.
        query_params: Optional query parameters dictionary.

    Returns:
        Tuple of (token, source) or (None, None) if not found.

    Example:
        ```python
        token, source = extract_token(request.headers, request.cookies)
        if token:
            print(f"Token from {source.value}")
        ```
    """
    # 1. Try Bearer token
    token = extract_bearer_token(headers)
    if token:
        return token, TokenSource.HEADER

    # 2. Try API key
    api_key = extract_api_key(headers)
    if api_key:
        return api_key, TokenSource.API_KEY

    # 3. Try cookie
    if cookies:
        token = cookies.get("access_token")
        if token:
            return token, TokenSource.COOKIE

    # 4. Try query parameter
    if query_params:
        token = query_params.get("access_token")
        if token:
            return token, TokenSource.QUERY

    return None, None


def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA-256.

    API keys are stored hashed for security.
    Only the prefix (first 8 chars) is stored in plaintext for lookup.

    Args:
        api_key: The API key to hash.

    Returns:
        SHA-256 hash of the key.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_api_key(prefix: str = "sk") -> str:
    """Generate a new API key.

    Format: {prefix}_{random_32_chars}

    Args:
        prefix: Key prefix (default: "sk").

    Returns:
        Generated API key.

    Example:
        ```python
        api_key = generate_api_key("pk")  # pk_xxxxx...
        ```
    """
    random_part = secrets.token_urlsafe(24)  # ~32 chars
    return f"{prefix}_{random_part}"


def get_api_key_prefix(api_key: str) -> str:
    """Get the prefix (first 8 chars) of an API key for lookup.

    API keys should be longer than 8 characters so that the prefix
    is unique enough for storage lookup. Keys shorter than 8 chars
    will return the full key as prefix (ambiguous if multiple short keys exist).

    Args:
        api_key: The full API key.

    Returns:
        First 8 characters of the key.
    """
    return api_key[:8]


class TokenExtractor:
    """Utility class for extracting tokens from requests.

    Provides methods for extracting tokens from different sources
    with configurable priority and validation.

    Example:
        ```python
        extractor = TokenExtractor(
            allow_query_params=True,
            cookie_name="session_token",
        )
        token, source = extractor.extract(request.headers, request.cookies)
        ```
    """

    def __init__(
        self,
        *,
        allow_cookies: bool = True,
        allow_query_params: bool = False,
        cookie_name: str = "access_token",
        query_param_name: str = "access_token",
        allow_api_key: bool = True,
    ) -> None:
        """Initialize the token extractor.

        Args:
            allow_cookies: Whether to check cookies for tokens.
            allow_query_params: Whether to check query parameters for tokens.
            cookie_name: Name of the cookie to check.
            query_param_name: Name of the query parameter to check.
            allow_api_key: Whether to check for API key header.
        """
        self.allow_cookies = allow_cookies
        self.allow_query_params = allow_query_params
        self.cookie_name = cookie_name
        self.query_param_name = query_param_name
        self.allow_api_key = allow_api_key

    def extract(
        self,
        headers: dict[str, str],
        cookies: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> tuple[str | None, TokenSource | None]:
        """Extract token using configured settings.

        Args:
            headers: HTTP headers dictionary.
            cookies: Optional cookies dictionary.
            query_params: Optional query parameters dictionary.

        Returns:
            Tuple of (token, source) or (None, None).
        """
        # 1. Always try Bearer token first
        token = extract_bearer_token(headers)
        if token:
            return token, TokenSource.HEADER

        # 2. Try API key if allowed
        if self.allow_api_key:
            api_key = extract_api_key(headers)
            if api_key:
                return api_key, TokenSource.API_KEY

        # 3. Try cookie if allowed
        if self.allow_cookies and cookies:
            token = cookies.get(self.cookie_name)
            if token:
                return token, TokenSource.COOKIE

        # 4. Try query param if allowed
        if self.allow_query_params and query_params:
            token = query_params.get(self.query_param_name)
            if token:
                return token, TokenSource.QUERY

        return None, None


__all__: list[str] = [
    "TokenSource",
    "extract_bearer_token",
    "extract_api_key",
    "extract_token",
    "hash_api_key",
    "generate_api_key",
    "get_api_key_prefix",
    "TokenExtractor",
]
