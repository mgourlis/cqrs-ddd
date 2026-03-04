"""Handler/command decorators for authorization metadata.

Decorators set metadata on commands/handlers that
``DecoratorAuthorizationMiddleware`` reads at runtime to enforce
authorization before handler execution.

Each decorator accepts a **single value** or a **list** of values
together with a *qualifier* (``"all"`` | ``"any"`` | ``"not"``):

.. code-block:: python

    @requires_permission("order:read")                            # single
    @requires_permission(["order:read", "order:write"], "any")    # any of
    @requires_role(["admin", "editor"], "any")                    # any role
    @requires_role("guest", "not")                                # deny guest
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .models import AuthorizationConfig

Qualifier = Literal["all", "any", "not"]


# ---------------------------------------------------------------------------
# Requirement data-classes (stored as handler metadata)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PermissionRequirement:
    """Structured permission check stored on the handler class."""

    permissions: tuple[str, ...]
    qualifier: Qualifier = "all"


@dataclass(frozen=True)
class RoleRequirement:
    """Structured role check stored on the handler class."""

    roles: tuple[str, ...]
    qualifier: Qualifier = "all"


@dataclass(frozen=True)
class OwnershipRequirement:
    """Ownership metadata stored on the handler class."""

    resource_type: str
    id_field: str = "id"


# ---------------------------------------------------------------------------
# Decorator helpers
# ---------------------------------------------------------------------------

_PERM_ATTR = "__access_permission__"
_ROLE_ATTR = "__access_role__"
_OWNER_ATTR = "__access_owner__"
_AUTH_CFG_ATTR = "__authorization_config__"


def _normalize(value: str | list[str]) -> tuple[str, ...]:
    """Normalise a single string or list to a tuple."""
    if isinstance(value, str):
        return (value,)
    return tuple(value)


# ---------------------------------------------------------------------------
# Public decorators
# ---------------------------------------------------------------------------


def requires_permission(
    permission: str | list[str],
    qualifier: Qualifier = "all",
) -> Any:
    """Set :class:`PermissionRequirement` on the handler class.

    ``DecoratorAuthorizationMiddleware`` reads *__access_permission__*
    and enforces accordingly.

    Parameters
    ----------
    permission:
        A single permission string or a list of permission strings.
    qualifier:
        ``"all"`` — principal must have **every** permission (default).
        ``"any"`` — principal must have **at least one**.
        ``"not"`` — principal must have **none** of them.
    """

    def decorator(cls: type) -> type:
        req = PermissionRequirement(
            permissions=_normalize(permission),
            qualifier=qualifier,
        )
        setattr(cls, _PERM_ATTR, req)
        return cls

    return decorator


def requires_role(
    role: str | list[str],
    qualifier: Qualifier = "all",
) -> Any:
    """Set :class:`RoleRequirement` on the handler class.

    Parameters
    ----------
    role:
        A single role string or a list of role strings.
    qualifier:
        ``"all"`` — principal must hold **every** role (default).
        ``"any"`` — principal must hold **at least one**.
        ``"not"`` — principal must hold **none** of them.
    """

    def decorator(cls: type) -> type:
        req = RoleRequirement(
            roles=_normalize(role),
            qualifier=qualifier,
        )
        setattr(cls, _ROLE_ATTR, req)
        return cls

    return decorator


def requires_owner(resource_type: str, id_field: str = "id") -> Any:
    """Set :class:`OwnershipRequirement` on the handler class.

    ``DecoratorAuthorizationMiddleware`` uses ``IOwnershipResolver``
    to verify the current principal owns the target resource.
    """

    def decorator(cls: type) -> type:
        req = OwnershipRequirement(resource_type=resource_type, id_field=id_field)
        setattr(cls, _OWNER_ATTR, req)
        return cls

    return decorator


def authorization(
    resource_type: str | None = None,
    resource_type_attr: str | None = None,
    required_actions: list[str] | None = None,
    resource_id_attr: str | None = None,
    **kwargs: Any,
) -> Any:
    """Set full :class:`AuthorizationConfig` metadata on the handler class.

    This is the most flexible decorator — allows full ABAC/ACL middleware
    configuration per-handler.
    """

    def decorator(cls: type) -> type:
        config = AuthorizationConfig(
            resource_type=resource_type,
            resource_type_attr=resource_type_attr,
            required_actions=required_actions or [],
            resource_id_attr=resource_id_attr,
            **kwargs,
        )
        setattr(cls, _AUTH_CFG_ATTR, config)
        return cls

    return decorator


# ---------------------------------------------------------------------------
# Metadata readers (used by DecoratorAuthorizationMiddleware)
# ---------------------------------------------------------------------------


def get_permission_requirement(cls: type) -> PermissionRequirement | None:
    """Read the :class:`PermissionRequirement` set by ``@requires_permission``."""
    return getattr(cls, _PERM_ATTR, None)


def get_role_requirement(cls: type) -> RoleRequirement | None:
    """Read the :class:`RoleRequirement` set by ``@requires_role``."""
    return getattr(cls, _ROLE_ATTR, None)


def get_ownership_requirement(cls: type) -> OwnershipRequirement | None:
    """Read the :class:`OwnershipRequirement` set by ``@requires_owner``."""
    return getattr(cls, _OWNER_ATTR, None)


def get_authorization_config(cls: type) -> AuthorizationConfig | None:
    """Read the :class:`AuthorizationConfig` set by ``@authorization``."""
    return getattr(cls, _AUTH_CFG_ATTR, None)
