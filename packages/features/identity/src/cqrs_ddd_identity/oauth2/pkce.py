"""OAuth2 PKCE (Proof Key for Code Exchange) utilities.

PKCE prevents authorization code interception attacks by requiring
the client to prove possession of the code_verifier.

RFC 7636: https://datatracker.ietf.org/doc/html/rfc7636
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PKCEData:
    """PKCE verification data.

    Attributes:
        code_verifier: Random string (43-128 chars) used to verify the exchange.
        code_challenge: S256 hash of the verifier sent in authorize request.
        code_challenge_method: Always "S256" for SHA256.
    """

    code_verifier: str
    code_challenge: str
    code_challenge_method: Literal["S256"] = "S256"


def generate_pkce_verifier(length: int = 64) -> str:
    """Generate a cryptographically random code_verifier.

    The code_verifier must be between 43 and 128 characters and use only
    unreserved characters: A-Z, a-z, 0-9, -, ., _, ~

    Args:
        length: Length of verifier (default 64, range 43-128).

    Returns:
        URL-safe random string.

    Raises:
        ValueError: If length is outside valid range.

    Example:
        ```python
        verifier = generate_pkce_verifier()
        # Returns: "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        ```
    """
    if length < 43 or length > 128:
        raise ValueError("code_verifier length must be between 43 and 128 characters")

    # Generate random bytes and encode as URL-safe base64
    random_bytes = secrets.token_bytes(length)
    # Use urlsafe_b64encode and strip padding
    verifier = base64.urlsafe_b64encode(random_bytes).decode().rstrip("=")

    # Ensure we're within bounds after stripping padding
    # Each 3 bytes become 4 chars, so 64 bytes → 85+ chars before stripping
    # We need to truncate to desired length
    return verifier[:length]


def generate_pkce_challenge(verifier: str) -> str:
    """Generate code_challenge from code_verifier using S256 method.

    code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))

    Args:
        verifier: The code_verifier string.

    Returns:
        S256 code_challenge string.

    Example:
        ```python
        verifier = generate_pkce_verifier()
        challenge = generate_pkce_challenge(verifier)
        # Use challenge in authorization URL
        ```
    """
    # Hash the verifier
    digest = hashlib.sha256(verifier.encode()).digest()

    # Base64 URL encode without padding
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def create_pkce_data(verifier_length: int = 64) -> PKCEData:
    """Create complete PKCE data with verifier and challenge.

    Convenience function that generates both the verifier and challenge.

    Args:
        verifier_length: Length of code_verifier (default 64).

    Returns:
        PKCEData with verifier, challenge, and method.

    Example:
        ```python
        pkce = create_pkce_data()
        # pkce.code_verifier -> "random_string..."
        # pkce.code_challenge -> "hashed_value..."
        ```
    """
    verifier = generate_pkce_verifier(verifier_length)
    challenge = generate_pkce_challenge(verifier)
    return PKCEData(code_verifier=verifier, code_challenge=challenge)


def verify_pkce_challenge(verifier: str, challenge: str) -> bool:
    """Verify that a code_verifier matches a code_challenge.

    This is called during the token exchange to verify the client
    possesses the original code_verifier.

    Args:
        verifier: The code_verifier from the token request.
        challenge: The code_challenge from the authorization request.

    Returns:
        True if verifier produces the challenge, False otherwise.

    Example:
        ```python
        # During callback - retrieve state data safely
        state_data = await session_store.get("oauth_state:state_value")
        if state_data is None:
            raise OAuthStateError("Invalid OAuth state")

        stored_challenge = state_data.get("code_challenge")
        provided_verifier = request.form["code_verifier"]

        if not stored_challenge or not verify_pkce_challenge(
            provided_verifier, stored_challenge
        ):
            raise PKCEValidationError("Invalid PKCE verifier")
        ```
    """
    if not verifier or not challenge:
        return False

    # Verify length constraints
    if len(verifier) < 43 or len(verifier) > 128:
        return False

    # Compute challenge from verifier
    computed_challenge = generate_pkce_challenge(verifier)

    # Constant-time comparison to prevent timing attacks
    return secrets.compare_digest(computed_challenge, challenge)


__all__: list[str] = [
    "PKCEData",
    "generate_pkce_verifier",
    "generate_pkce_challenge",
    "create_pkce_data",
    "verify_pkce_challenge",
]
