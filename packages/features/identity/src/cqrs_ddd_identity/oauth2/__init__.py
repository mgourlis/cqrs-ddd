"""OAuth2 module for cqrs-ddd-identity."""

from .client import OAuth2ProviderConfig, OAuth2TokenClient
from .pkce import (
    PKCEData,
    create_pkce_data,
    generate_pkce_challenge,
    generate_pkce_verifier,
    verify_pkce_challenge,
)
from .state import OAuthStateData, OAuthStateManager, generate_oauth_state

# Keycloak support (requires [keycloak] extra)
try:
    from .keycloak import GroupPathStrategy, KeycloakConfig, KeycloakIdentityProvider
except ImportError:
    # python-keycloak not installed
    GroupPathStrategy = None  # type: ignore[misc,assignment]
    KeycloakConfig = None  # type: ignore[misc,assignment]
    KeycloakIdentityProvider = None  # type: ignore[misc,assignment]

__all__: list[str] = [
    # Client
    "OAuth2ProviderConfig",
    "OAuth2TokenClient",
    # PKCE
    "PKCEData",
    "generate_pkce_verifier",
    "generate_pkce_challenge",
    "create_pkce_data",
    "verify_pkce_challenge",
    # State
    "OAuthStateData",
    "generate_oauth_state",
    "OAuthStateManager",
    # Keycloak (optional)
    "GroupPathStrategy",
    "KeycloakConfig",
    "KeycloakIdentityProvider",
]
