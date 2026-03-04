"""Access-control middleware components."""

from __future__ import annotations

from .authorization import AuthorizationMiddleware
from .decorator_middleware import DecoratorAuthorizationMiddleware
from .permitted_actions import PermittedActionsMiddleware
from .specification import SpecificationAuthMiddleware

__all__ = [
    "AuthorizationMiddleware",
    "DecoratorAuthorizationMiddleware",
    "PermittedActionsMiddleware",
    "SpecificationAuthMiddleware",
]
