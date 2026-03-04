"""ACL evaluator — wraps IAuthorizationPort for per-resource ACL decisions."""

from __future__ import annotations

from cqrs_ddd_identity import Principal, get_access_token

from ..models import AuthorizationContext, AuthorizationDecision
from ..ports import IAuthorizationPort
from .base import IPermissionEvaluator


class ACLEvaluator(IPermissionEvaluator):
    """Per-resource ACL checks via ``IAuthorizationPort.check_access()``.

    Deny overrides grant. Missing ACL entries → abstain.
    """

    def __init__(self, authorization_port: IAuthorizationPort) -> None:
        self._port = authorization_port

    async def evaluate(
        self,
        _principal: Principal,
        context: AuthorizationContext,
    ) -> AuthorizationDecision:
        access_token = get_access_token()
        authorized_ids = await self._port.check_access(
            access_token,
            context.resource_type,
            context.action,
            resource_ids=context.resource_ids,
            auth_context=context.auth_context,
        )

        # Type-level check (no specific resource IDs)
        if context.resource_ids is None:
            if authorized_ids:
                return AuthorizationDecision(
                    allowed=True,
                    reason="Type-level ACL granted",
                    evaluator="acl",
                )
            return AuthorizationDecision(
                allowed=False, reason="abstain", evaluator="acl"
            )

        # Resource-level check
        if set(context.resource_ids) <= set(authorized_ids):
            return AuthorizationDecision(
                allowed=True,
                reason="ACL grant for all requested resources",
                evaluator="acl",
            )

        denied_ids = set(context.resource_ids) - set(authorized_ids)
        if denied_ids:
            return AuthorizationDecision(
                allowed=False,
                reason=f"ACL denied for resources: {denied_ids}",
                evaluator="acl",
            )

        return AuthorizationDecision(allowed=False, reason="abstain", evaluator="acl")
