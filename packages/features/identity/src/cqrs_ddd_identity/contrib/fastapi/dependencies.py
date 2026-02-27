"""FastAPI dependencies for authentication.

Provides Depends functions for injecting principals into route handlers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException

from ...context import (
    get_current_principal,
    get_current_principal_or_none,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ...principal import Principal


def get_principal() -> Principal:
    """Get current principal or raise 401.

    Use this as a FastAPI dependency when authentication is required.

    Returns:
        The current Principal.

    Raises:
        HTTPException: 401 if not authenticated.

    Example:
        ```python
        from fastapi import APIRouter, Depends
        from cqrs_ddd_identity.contrib.fastapi import get_principal

        router = APIRouter()

        @router.get("/me")
        def get_me(principal = Depends(get_principal)):
            return {"user_id": principal.user_id}
        ```
    """
    try:
        return get_current_principal()
    except LookupError as err:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err


def get_principal_optional() -> Principal | None:
    """Get current principal or None.

    Use this when authentication is optional.

    Returns:
        The current Principal or None.

    Example:
        ```python
        @router.get("/public")
        def get_public(principal = Depends(get_principal_optional)):
            if principal:
                return {"user": principal.username}
            return {"user": "anonymous"}
        ```
    """
    return get_current_principal_or_none()


def require_role(role: str) -> Callable[[Any], Principal]:
    """Create a dependency that requires a specific role.

    Args:
        role: Required role name.

    Returns:
        Dependency function.

    Example:
        ```python
        @router.get("/admin")
        def admin_only(principal = Depends(require_role("admin"))):
            return {"message": "Admin access granted"}
        ```
    """

    def dependency(
        principal: Principal = Depends(get_principal),  # noqa: B008
    ) -> Principal:
        if not principal.has_role(role):
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' required",
            )
        return principal

    return dependency


def require_permission(permission: str) -> Callable[[Any], Principal]:
    """Create a dependency that requires a specific permission.

    Args:
        permission: Required permission string.

    Returns:
        Dependency function.

    Example:
        ```python
        @router.post("/orders")
        def create_order(
            principal = Depends(require_permission("write:orders"))
        ):
            # Only users with write:orders permission reach here
            pass
        ```
    """

    def dependency(
        principal: Principal = Depends(get_principal),  # noqa: B008
    ) -> Principal:
        if not principal.has_permission(permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{permission}' required",
            )
        return principal

    return dependency


def require_roles(*roles: str) -> Callable[[Any], Principal]:
    """Create a dependency that requires all specified roles.

    Args:
        *roles: Required role names.

    Returns:
        Dependency function.
    """

    def dependency(
        principal: Principal = Depends(get_principal),  # noqa: B008
    ) -> Principal:
        missing = [r for r in roles if not principal.has_role(r)]
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Roles required: {', '.join(missing)}",
            )
        return principal

    return dependency


def require_any_role(*roles: str) -> Callable[[Any], Principal]:
    """Create a dependency that requires any of the specified roles.

    Args:
        *roles: Role names (any one required).

    Returns:
        Dependency function.
    """

    def dependency(
        principal: Principal = Depends(get_principal),  # noqa: B008
    ) -> Principal:
        if not principal.has_any_role(*roles):
            raise HTTPException(
                status_code=403,
                detail=f"One of these roles required: {', '.join(roles)}",
            )
        return principal

    return dependency


def require_authenticated() -> Principal:
    """Require authenticated user (alias for get_principal).

    Returns:
        The current Principal.

    Raises:
        HTTPException: 401 if not authenticated.
    """
    return get_principal()


__all__: list[str] = [
    "get_principal",
    "get_principal_optional",
    "require_role",
    "require_permission",
    "require_roles",
    "require_any_role",
    "require_authenticated",
]
