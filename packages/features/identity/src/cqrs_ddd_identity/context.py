"""Principal context management using ContextVar.

Provides async-safe context variables for storing the current principal
without passing it through function parameters.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .principal import Principal


# Context variables for request-scoped authentication data
_principal_context: ContextVar[Principal | None] = ContextVar("principal", default=None)
_access_token_context: ContextVar[str | None] = ContextVar("access_token", default=None)
_refresh_token_context: ContextVar[str | None] = ContextVar(
    "refresh_token", default=None
)


def get_current_principal() -> Principal:
    """Get current principal from context.

    Returns:
        The current Principal from context.

    Raises:
        LookupError: If no principal is set in the context.

    Example:
        ```python
        # In a request handler or domain service
        principal = get_current_principal()
        print(f"Current user: {principal.username}")
        ```
    """

    principal = _principal_context.get()
    if principal is None:
        raise LookupError(
            "No principal in context. Ensure AuthenticationMiddleware is configured."
        )
    return principal


def get_current_principal_or_none() -> Principal | None:
    """Get current principal from context or None.

    Use this when authentication is optional and you want to handle
    unauthenticated requests gracefully.

    Returns:
        The current Principal or None if not set.

    Example:
        ```python
        principal = get_current_principal_or_none()
        if principal and principal.has_permission("read:orders"):
            # Show order details
            pass
        else:
            # Show limited view
            pass
        ```
    """
    return _principal_context.get()


def set_principal(principal: Principal) -> Token[Principal | None]:
    """Set principal in current async context.

    Args:
        principal: The Principal to set in context.

    Returns:
        A Token that can be used to reset the context variable.

    Example:
        ```python
        token = set_principal(principal)
        try:
            # Process request
            pass
        finally:
            reset_principal(token)
        ```
    """
    return _principal_context.set(principal)


def reset_principal(token: Token[Principal | None]) -> None:
    """Reset principal context to previous state.

    Use this to clean up after setting a principal, typically in a finally block.

    Args:
        token: The Token returned by set_principal().

    Example:
        ```python
        token = set_principal(principal)
        try:
            # Do work
            pass
        finally:
            reset_principal(token)
        ```
    """
    _principal_context.reset(token)


def clear_principal() -> None:
    """Clear principal from context.

    Sets the context to None. Use this for cleanup when you don't
    need to restore a previous value.

    Example:
        ```python
        try:
            principal = await identity_provider.resolve(token)
            set_principal(principal)
            return await call_next(request)
        finally:
            clear_principal()  # Prevent context leakage
        ```
    """
    _principal_context.set(None)


def get_user_id() -> str:
    """Get current user ID from context.

    Convenience function for the common case of needing just the user ID.

    Returns:
        The current user's ID.

    Raises:
        LookupError: If no principal is set in context.

    Example:
        ```python
        user_id = get_user_id()
        order = await repo.get_by_user(user_id)
        ```
    """
    return get_current_principal().user_id


def get_user_id_or_none() -> str | None:
    """Get current user ID from context or None.

    Returns:
        The current user's ID or None if not authenticated.
    """
    principal = get_current_principal_or_none()
    return principal.user_id if principal else None


def get_tenant_id() -> str | None:
    """Get current tenant ID from context.

    Returns:
        The current tenant ID or None if not set.

    Example:
        ```python
        tenant_id = get_tenant_id()
        if tenant_id:
            orders = await repo.list_by_tenant(tenant_id)
        ```
    """
    principal = get_current_principal_or_none()
    return principal.tenant_id if principal else None


def is_authenticated() -> bool:
    """Check if there is an authenticated principal in context.

    Returns:
        True if there is a non-anonymous principal in context.

    Example:
        ```python
        if is_authenticated():
            # Show personalized content
            pass
        ```
    """
    principal = get_current_principal_or_none()
    return principal is not None and principal.is_authenticated


def require_role(role: str) -> None:
    """Require the current principal to have a specific role.

    Args:
        role: The required role name.

    Raises:
        LookupError: If no principal is in context.
        IdentityPermissionError: If principal doesn't have the required role.

    Example:
        ```python
        require_role("admin")
        # Only admins reach here
        ```
    """
    from .exceptions import IdentityPermissionError

    principal = get_current_principal()
    if not principal.has_role(role):
        raise IdentityPermissionError(f"Role '{role}' required")


def require_permission(permission: str) -> None:
    """Require the current principal to have a specific permission.

    Args:
        permission: The required permission string.

    Raises:
        LookupError: If no principal is in context.
        IdentityPermissionError: If principal doesn't have the required permission.

    Example:
        ```python
        require_permission("write:orders")
        # Only users with write:orders reach here
        ```
    """
    from .exceptions import IdentityPermissionError

    principal = get_current_principal()
    if not principal.has_permission(permission):
        raise IdentityPermissionError(f"Permission '{permission}' required")


def require_authenticated() -> None:
    """Require an authenticated principal in context.

    Raises:
        LookupError: If no principal is in context or it's anonymous.

    Example:
        ```python
        require_authenticated()
        # Only authenticated users reach here
        ```
    """
    principal = get_current_principal()
    if not principal.is_authenticated:
        raise LookupError("Authentication required")


# ═══════════════════════════════════════════════════════════════
# TOKEN CONTEXT MANAGEMENT
# ═══════════════════════════════════════════════════════════════


def get_access_token() -> str | None:
    """Get the current access token from context.

    The access token is stored by authentication middleware and can be
    used for downstream service calls or token introspection.

    Returns:
        The current access token or None if not set.

    Example:
        ```python
        token = get_access_token()
        if token:
            headers = {"Authorization": f"Bearer {token}"}
            response = await http_client.get(url, headers=headers)
        ```
    """
    return _access_token_context.get()


def set_access_token(token: str | None) -> Token[str | None]:
    """Set access token in current async context.

    Args:
        token: The access token to set, or None to clear.

    Returns:
        A Token that can be used to reset the context variable.

    Example:
        ```python
        token = set_access_token(bearer_token)
        try:
            # Process request
            pass
        finally:
            reset_access_token(token)
        ```
    """
    return _access_token_context.set(token)


def reset_access_token(token: Token[str | None]) -> None:
    """Reset access token context to previous state.

    Args:
        token: The Token returned by set_access_token().
    """
    _access_token_context.reset(token)


def get_refresh_token() -> str | None:
    """Get the current refresh token from context.

    Returns:
        The current refresh token or None if not set.
    """
    return _refresh_token_context.get()


def set_refresh_token(token: str | None) -> Token[str | None]:
    """Set refresh token in current async context.

    Args:
        token: The refresh token to set, or None to clear.

    Returns:
        A Token that can be used to reset the context variable.
    """
    return _refresh_token_context.set(token)


def reset_refresh_token(token: Token[str | None]) -> None:
    """Reset refresh token context to previous state.

    Args:
        token: The Token returned by set_refresh_token().
    """
    _refresh_token_context.reset(token)


def set_tokens(
    access_token: str | None, refresh_token: str | None
) -> tuple[Token[str | None], Token[str | None]]:
    """Set both access and refresh tokens in context.

    Convenience function for setting both tokens at once.

    Args:
        access_token: The access token to set.
        refresh_token: The refresh token to set.

    Returns:
        Tuple of tokens for resetting (access_token_token, refresh_token_token).

    Example:
        ```python
        access_token, refresh_token = set_tokens(access, refresh)
        try:
            # Process request
            pass
        finally:
            reset_tokens(access_token, refresh_token)
        ```
    """
    return set_access_token(access_token), set_refresh_token(refresh_token)


def reset_tokens(
    access_token: Token[str | None],
    refresh_token: Token[str | None],
) -> None:
    """Reset both access and refresh token contexts.

    Args:
        access_token: The Token returned for access token.
        refresh_token: The Token returned for refresh token.
    """
    reset_access_token(access_token)
    reset_refresh_token(refresh_token)


def clear_tokens() -> None:
    """Clear both access and refresh tokens from context.

    Example:
        ```python
        try:
            # Process request
            pass
        finally:
            clear_tokens()  # Prevent token leakage
        ```
    """
    _access_token_context.set(None)
    _refresh_token_context.set(None)


def get_authorization_header() -> str | None:
    """Get the Authorization header value for downstream calls.

    Returns a properly formatted Bearer token header value if an
    access token is available in context.

    Returns:
        "Bearer <token>" or None if no access token is set.

    Example:
        ```python
        headers = {}
        auth = get_authorization_header()
        if auth:
            headers["Authorization"] = auth
        response = await http_client.get(url, headers=headers)
        ```
    """
    token = get_access_token()
    if token:
        return f"Bearer {token}"
    return None


__all__: list[str] = [
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
    "require_authenticated",  # Token context
    "get_access_token",
    "set_access_token",
    "reset_access_token",
    "get_refresh_token",
    "set_refresh_token",
    "reset_refresh_token",
    "set_tokens",
    "reset_tokens",
    "clear_tokens",
    "get_authorization_header",
]
