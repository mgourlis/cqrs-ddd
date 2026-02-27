"""FastAPI integration for cqrs-ddd-identity."""

from .dependencies import (
    get_principal,
    get_principal_optional,
    require_any_role,
    require_authenticated,
    require_permission,
    require_role,
    require_roles,
)
from .middleware import AuthenticationMiddleware
from .token_refresh import (
    TokenRefreshAdapter,
    TokenRefreshConfig,
    TokenRefreshMiddleware,
)

__all__: list[str] = [
    # Middleware
    "AuthenticationMiddleware",
    "TokenRefreshMiddleware",
    # Token Refresh
    "TokenRefreshConfig",
    "TokenRefreshAdapter",
    # Dependencies
    "get_principal",
    "get_principal_optional",
    "require_role",
    "require_permission",
    "require_roles",
    "require_any_role",
    "require_authenticated",
]
