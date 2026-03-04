"""RBAC evaluator — role-to-permission mapping with optional hierarchy."""

from __future__ import annotations

from cqrs_ddd_identity import Principal

from ..models import AuthorizationContext, AuthorizationDecision
from .base import IPermissionEvaluator

# Type alias for role → set of permission strings mapping.
RolePermissionMap = dict[str, set[str]]
# Type alias for role hierarchy: parent → set of children.
RoleHierarchy = dict[str, set[str]]


class RBACEvaluator(IPermissionEvaluator):
    """Check ``Principal.roles`` against a configurable permission map.

    Permission format: ``"{resource_type}:{action}"``

    Parameters
    ----------
    role_permissions:
        Mapping of role name → set of permission strings.
    role_hierarchy:
        Optional hierarchy mapping parent → children. Permissions
        are inherited downward (parent inherits children's permissions).
    """

    def __init__(
        self,
        role_permissions: RolePermissionMap,
        role_hierarchy: RoleHierarchy | None = None,
    ) -> None:
        self._role_permissions = role_permissions
        self._role_hierarchy = role_hierarchy or {}

    async def evaluate(
        self,
        principal: Principal,
        context: AuthorizationContext,
    ) -> AuthorizationDecision:
        expanded_roles = self._expand_roles(principal.roles)
        permission_key = f"{context.resource_type}:{context.action}"

        permissions: set[str] = set()
        for role in expanded_roles:
            permissions |= self._role_permissions.get(role, set())

        if permission_key in permissions:
            return AuthorizationDecision(
                allowed=True,
                reason=f"Role permission match: {permission_key}",
                evaluator="rbac",
            )
        return AuthorizationDecision(
            allowed=False,
            reason="abstain",
            evaluator="rbac",
        )

    def _expand_roles(self, roles: frozenset[str]) -> set[str]:
        """Expand roles via hierarchy (parent inherits children)."""
        expanded: set[str] = set(roles)
        queue = list(roles)
        while queue:
            role = queue.pop()
            for child in self._role_hierarchy.get(role, set()):
                if child not in expanded:
                    expanded.add(child)
                    queue.append(child)
        return expanded
