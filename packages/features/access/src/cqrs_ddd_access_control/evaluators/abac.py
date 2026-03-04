"""ABAC connector — delegates to an external authorization engine."""

from __future__ import annotations

from cqrs_ddd_identity import Principal, get_access_token

from ..models import AuthorizationContext, AuthorizationDecision
from ..ports import IAuthorizationPort
from .base import IPermissionEvaluator


class ABACConnector(IPermissionEvaluator):
    """Delegates to an external authorization engine via ``IAuthorizationPort``.

    Works with stateful-abac, OPA, Casbin, or any custom backend.
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

        # Type-level check
        if context.resource_ids is None:
            if authorized_ids:
                return AuthorizationDecision(
                    allowed=True,
                    reason="ABAC engine granted type-level access",
                    evaluator="abac",
                )
            return AuthorizationDecision(
                allowed=False,
                reason="ABAC engine denied type-level access",
                evaluator="abac",
            )

        # Resource-level check
        if set(context.resource_ids) <= set(authorized_ids):
            return AuthorizationDecision(
                allowed=True,
                reason="ABAC engine granted access",
                evaluator="abac",
            )

        return AuthorizationDecision(
            allowed=False,
            reason="ABAC engine denied access",
            evaluator="abac",
        )
