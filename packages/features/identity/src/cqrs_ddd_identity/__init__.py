"""CQRS-DDD Identity Package

Authentication — "Who are you?"

Resolves bearer tokens to an immutable Principal value object via IIdentityProvider.
Supports OAuth 2.0 / OIDC flows and optional two-factor authentication (2FA).

Usage:
    ```python
    from cqrs_ddd_identity import (
        Principal,
        get_current_principal,
        IIdentityProvider,
        AuthenticationError,
    )

    # Get the current principal in a request context
    principal = get_current_principal()
    print(f"User: {principal.username}")

    # Check permissions
    if principal.has_permission("write:orders"):
        # Allow order modification
        pass
    ```

Submodules:
    - `oauth2`: OAuth2/OIDC client, PKCE, state management
    - `mfa`: MFA ports and backup codes
    - `db`: Database authentication with password hashing
    - `api_key`: API key authentication
    - `contrib.fastapi`: FastAPI middleware and dependencies
"""

from __future__ import annotations

# Audit
from .audit import (
    AuthAuditEvent,
    AuthEventType,
    InMemoryAuthAuditStore,
    api_key_used_event,
    login_failed_event,
    login_success_event,
    logout_event,
    mfa_verified_event,
    session_created_event,
    session_destroyed_event,
    token_refreshed_event,
)

# Context management
from .context import (
    clear_principal,
    clear_tokens,
    get_access_token,
    get_authorization_header,
    get_current_principal,
    get_current_principal_or_none,
    get_refresh_token,
    get_tenant_id,
    get_user_id,
    get_user_id_or_none,
    is_authenticated,
    require_authenticated,
    require_permission,
    require_role,
    reset_principal,
    set_access_token,
    set_principal,
    set_refresh_token,
    set_tokens,
)

# Exceptions
from .exceptions import (
    AccountLockedError,
    ApiKeyError,
    AuthenticationError,
    BackupCodeExhaustedError,
    ExpiredApiKeyError,
    ExpiredTokenError,
    IdentityError,
    IdentityPermissionError,
    InvalidApiKeyError,
    InvalidCredentialsError,
    InvalidTokenError,
    MfaError,
    MfaInvalidError,
    MfaRequiredError,
    MfaSetupError,
    OAuthCallbackError,
    OAuthError,
    OAuthStateError,
    PKCEValidationError,
    SessionError,
    SessionExpiredError,
    SessionInvalidError,
)

# Factory
from .factory import (
    CompositeIdentityProvider,
    create_api_only_provider,
    create_composite_provider,
    create_hybrid_provider,
)

# Ports
from .ports import (
    ApiKeyRecord,
    IApiKeyRepository,
    IAuthAuditStore,
    IIdentityProvider,
    ILockoutStore,
    ISessionStore,
    ITokenValidator,
    IUserCredentialsRepository,
    TokenResponse,
    UserCredentials,
)

# Principal value object
from .principal import Principal

# Request context
from .request_context import (
    RequestContext,
    get_client_ip,
    get_request_context,
    get_request_id,
    get_user_agent,
)

# Session
from .session import InMemorySessionStore

# Token utilities
from .token import (
    TokenExtractor,
    TokenSource,
    extract_api_key,
    extract_bearer_token,
    extract_token,
    generate_api_key,
    get_api_key_prefix,
    hash_api_key,
)

__all__: list[str] = [
    # Principal
    "Principal",
    # Exceptions
    "IdentityError",
    "AuthenticationError",
    "InvalidTokenError",
    "ExpiredTokenError",
    "InvalidCredentialsError",
    "AccountLockedError",
    "IdentityPermissionError",
    "MfaError",
    "MfaRequiredError",
    "MfaInvalidError",
    "MfaSetupError",
    "BackupCodeExhaustedError",
    "OAuthError",
    "OAuthStateError",
    "OAuthCallbackError",
    "PKCEValidationError",
    "ApiKeyError",
    "InvalidApiKeyError",
    "ExpiredApiKeyError",
    "SessionError",
    "SessionExpiredError",
    "SessionInvalidError",
    # Context
    "get_current_principal",
    "get_current_principal_or_none",
    "set_principal",
    "reset_principal",
    "clear_principal",
    "get_user_id",
    "get_user_id_or_none",
    "get_tenant_id",
    "is_authenticated",
    "require_role",
    "require_permission",
    "require_authenticated",
    # Token context
    "get_access_token",
    "set_access_token",
    "get_refresh_token",
    "set_refresh_token",
    "set_tokens",
    "clear_tokens",
    "get_authorization_header",
    # Ports
    "IIdentityProvider",
    "ITokenValidator",
    "ISessionStore",
    "IUserCredentialsRepository",
    "UserCredentials",
    "IApiKeyRepository",
    "ApiKeyRecord",
    "ILockoutStore",
    "IAuthAuditStore",
    "TokenResponse",
    # Session
    "InMemorySessionStore",
    # Token utilities
    "TokenSource",
    "extract_bearer_token",
    "extract_api_key",
    "extract_token",
    "hash_api_key",
    "generate_api_key",
    "get_api_key_prefix",
    "TokenExtractor",
    # Audit
    "AuthEventType",
    "AuthAuditEvent",
    "InMemoryAuthAuditStore",
    "login_success_event",
    "login_failed_event",
    "logout_event",
    "token_refreshed_event",
    "mfa_verified_event",
    "api_key_used_event",
    "session_created_event",
    "session_destroyed_event",
    # Factory
    "CompositeIdentityProvider",
    "create_composite_provider",
    "create_hybrid_provider",
    "create_api_only_provider",
    # Request Context
    "RequestContext",
    "get_request_context",
    "get_request_id",
    "get_client_ip",
    "get_user_agent",
]

__version__ = "0.1.0"
