"""Ownership evaluator — resource.owner_id == principal.user_id."""

from __future__ import annotations

from cqrs_ddd_identity import Principal

from ..models import AuthorizationContext, AuthorizationDecision
from ..ports import IOwnershipResolver
from .base import IPermissionEvaluator


class OwnershipEvaluator(IPermissionEvaluator):
    """Allow if principal is the owner of the resource.

    Parameters
    ----------
    ownership_resolver:
        Resolves owner user_id(s) for a resource.
    owner_actions:
        Actions the owner is permitted to perform. ``None`` = all actions.
    """

    def __init__(
        self,
        ownership_resolver: IOwnershipResolver,
        owner_actions: set[str] | None = None,
    ) -> None:
        self._resolver = ownership_resolver
        self._owner_actions = owner_actions

    async def evaluate(
        self,
        principal: Principal,
        context: AuthorizationContext,
    ) -> AuthorizationDecision:
        if not context.resource_ids:
            return AuthorizationDecision(
                allowed=False, reason="abstain", evaluator="ownership"
            )

        for resource_id in context.resource_ids:
            owner = await self._resolver.get_owner(context.resource_type, resource_id)
            if owner is None:
                return AuthorizationDecision(
                    allowed=False, reason="abstain", evaluator="ownership"
                )

            owners = owner if isinstance(owner, list) else [owner]
            if principal.user_id not in owners:
                return AuthorizationDecision(
                    allowed=False, reason="abstain", evaluator="ownership"
                )

        # Check action restriction
        if (
            self._owner_actions is not None
            and context.action not in self._owner_actions
        ):
            return AuthorizationDecision(
                allowed=False, reason="abstain", evaluator="ownership"
            )

        return AuthorizationDecision(
            allowed=True,
            reason="Owner access granted",
            evaluator="ownership",
        )
