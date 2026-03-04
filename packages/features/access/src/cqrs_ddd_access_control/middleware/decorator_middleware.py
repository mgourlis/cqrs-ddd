"""DecoratorAuthorizationMiddleware — enforcement based on handler metadata.

This middleware inspects the handler class (resolved from the
``HandlerRegistry``) for decorator metadata set by
``@requires_permission``, ``@requires_role``, ``@requires_owner``,
and ``@authorization``, then enforces the requirements **before**
the handler executes.

Usage::

    from cqrs_ddd_core.cqrs.registry import HandlerRegistry
    from cqrs_ddd_access_control.middleware import DecoratorAuthorizationMiddleware

    middleware = DecoratorAuthorizationMiddleware(
        handler_registry=registry,
        ownership_resolver=my_resolver,   # optional
    )
    middleware_registry.register(
        type(middleware), factory=lambda: middleware, priority=5
    )
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cqrs_ddd_identity import get_current_principal_or_none

from ..decorators import (
    get_authorization_config,
    get_ownership_requirement,
    get_permission_requirement,
    get_role_requirement,
)
from ..exceptions import InsufficientRoleError, PermissionDeniedError
from ..models import _resolve_bypass_roles

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from cqrs_ddd_core.cqrs.registry import HandlerRegistry

    from ..ports import IAuthorizationPort, IOwnershipResolver

logger = logging.getLogger(__name__)


class DecoratorAuthorizationMiddleware:
    """Middleware that reads decorator metadata from handler classes.

    The pipeline invokes ``__call__(message, next_handler)`` — this
    middleware resolves the handler class for the message type, inspects
    it for ``@requires_permission`` / ``@requires_role`` /
    ``@requires_owner`` / ``@authorization`` metadata, and enforces the
    requirements against the current principal.

    Parameters
    ----------
    handler_registry:
        Used to resolve the handler class for incoming messages.
    authorization_port:
        Optional — required only when ``@authorization`` is used.
    ownership_resolver:
        Optional — required only when ``@requires_owner`` is used.
    bypass_roles:
        Roles that skip all authorization checks.
    """

    def __init__(
        self,
        handler_registry: HandlerRegistry,
        *,
        authorization_port: IAuthorizationPort | None = None,
        ownership_resolver: IOwnershipResolver | None = None,
        bypass_roles: frozenset[str] | None = None,
    ) -> None:
        self._registry = handler_registry
        self._auth_port = authorization_port
        self._ownership_resolver = ownership_resolver
        self._bypass_roles = _resolve_bypass_roles(bypass_roles)

    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Enforce decorator-based authorization before calling handler."""
        principal = get_current_principal_or_none()

        # Bypass early for privileged roles
        if (
            principal
            and self._bypass_roles
            and principal.has_any_role(*self._bypass_roles)
        ):
            return await next_handler(message)

        # Resolve the handler class for this message type
        handler_cls = self._resolve_handler_class(message)
        if handler_cls is None:
            # No handler → nothing to enforce, let pipeline proceed
            return await next_handler(message)

        # ── @requires_permission ─────────────────────────────────
        perm_req = get_permission_requirement(handler_cls)
        if perm_req is not None:
            self._enforce_permission(principal, perm_req)

        # ── @requires_role ───────────────────────────────────────
        role_req = get_role_requirement(handler_cls)
        if role_req is not None:
            self._enforce_role(principal, role_req)

        # ── @requires_owner ──────────────────────────────────────
        owner_req = get_ownership_requirement(handler_cls)
        if owner_req is not None:
            await self._enforce_ownership(principal, message, owner_req)

        # ── @authorization ───────────────────────────────────────
        auth_config = get_authorization_config(handler_cls)
        if auth_config is not None and self._auth_port is not None:
            # Delegate to the existing AuthorizationMiddleware logic
            from .authorization import AuthorizationMiddleware

            inner = AuthorizationMiddleware(
                authorization_port=self._auth_port,
                config=auth_config,
                bypass_roles=self._bypass_roles,
            )
            return await inner(message, next_handler)

        return await next_handler(message)

    # ── Enforcement helpers ──────────────────────────────────────

    @staticmethod
    def _enforce_permission(principal: Any, req: Any) -> None:
        """Check permission requirement against principal."""
        if principal is None:
            msg = "Anonymous access denied"
            raise PermissionDeniedError(msg, reason=msg)

        perms = set(req.permissions)
        qualifier = req.qualifier

        if qualifier == "all":
            missing = [p for p in perms if not principal.has_permission(p)]
            if missing:
                msg = f"Missing permissions: {', '.join(missing)}"
                raise PermissionDeniedError(
                    msg,
                    reason=msg,
                    action=", ".join(perms),
                )
        elif qualifier == "any":
            if not any(principal.has_permission(p) for p in perms):
                msg = f"Requires any of: {', '.join(perms)}"
                raise PermissionDeniedError(
                    msg,
                    reason=msg,
                    action=", ".join(perms),
                )
        elif qualifier == "not":
            has = [p for p in perms if principal.has_permission(p)]
            if has:
                msg = f"Denied permissions present: {', '.join(has)}"
                raise PermissionDeniedError(
                    msg,
                    reason=msg,
                    action=", ".join(perms),
                )

    @staticmethod
    def _enforce_role(principal: Any, req: Any) -> None:
        """Check role requirement against principal."""
        if principal is None:
            msg = "Anonymous access denied"
            raise PermissionDeniedError(msg, reason=msg)

        roles = set(req.roles)
        qualifier = req.qualifier

        if qualifier == "all":
            missing = roles - principal.roles
            if missing:
                raise InsufficientRoleError(
                    required_role=", ".join(sorted(missing)),
                    message=f"Missing required roles: {', '.join(sorted(missing))}",
                )
        elif qualifier == "any":
            if not principal.has_any_role(*roles):
                raise InsufficientRoleError(
                    required_role=", ".join(sorted(roles)),
                    message=f"Requires any role of: {', '.join(sorted(roles))}",
                )
        elif qualifier == "not":
            has = roles & principal.roles
            if has:
                raise InsufficientRoleError(
                    required_role=", ".join(sorted(has)),
                    message=f"Denied roles present: {', '.join(sorted(has))}",
                )

    async def _enforce_ownership(self, principal: Any, message: Any, req: Any) -> None:
        """Check ownership via the configured resolver."""
        if principal is None:
            msg = "Anonymous access denied"
            raise PermissionDeniedError(msg, reason=msg)
        if self._ownership_resolver is None:
            logger.warning("@requires_owner used but no IOwnershipResolver configured")
            return

        resource_id = getattr(message, req.id_field, None)
        if resource_id is None:
            return  # no resource id to check

        owner_id = await self._ownership_resolver.get_owner(
            req.resource_type, str(resource_id)
        )
        if owner_id != principal.user_id:
            msg = "Ownership check failed"
            raise PermissionDeniedError(
                msg,
                resource_type=req.resource_type,
                resource_ids=[str(resource_id)],
                reason=msg,
            )

    # ── Handler resolution ───────────────────────────────────────

    def _resolve_handler_class(self, message: Any) -> type | None:
        """Resolve the handler class for a message from the registry."""
        message_type = type(message)

        # Try command handler first, then query handler
        cls = self._registry.get_command_handler(message_type)
        if cls is not None:
            return cls

        return self._registry.get_query_handler(message_type)
