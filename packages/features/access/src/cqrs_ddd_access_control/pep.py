"""Policy Enforcement Point — evaluator composition with deny-wins semantics."""

from __future__ import annotations

from cqrs_ddd_identity import Principal

from .evaluators.base import IPermissionEvaluator
from .models import (
    AuthorizationContext,
    AuthorizationDecision,
    _resolve_bypass_roles,
)
from .ports import IPermissionCache


class PolicyEnforcementPoint:
    """Compose evaluators. Deny-wins: any deny overrides all allows.

    Parameters
    ----------
    evaluators:
        Ordered list of evaluators to consult.
    cache:
        Optional permission cache.
    bypass_roles:
        Roles that skip all checks. Also reads ``AUTH_BYPASS_ROLES`` env.
    """

    def __init__(
        self,
        evaluators: list[IPermissionEvaluator],
        cache: IPermissionCache | None = None,
        bypass_roles: frozenset[str] | None = None,
    ) -> None:
        self._evaluators = evaluators
        self._cache = cache
        self._bypass_roles = _resolve_bypass_roles(bypass_roles)

    async def evaluate(
        self,
        principal: Principal,
        context: AuthorizationContext,
    ) -> AuthorizationDecision:
        """Compose evaluators with deny-wins semantics."""
        # Bypass roles
        if self._bypass_roles and principal.roles & self._bypass_roles:
            return AuthorizationDecision(
                allowed=True, reason="Bypass role", evaluator="pep"
            )

        # Check cache
        if self._cache is not None:
            cached = await self._cache.get(
                principal.user_id,
                context.resource_type,
                context.resource_ids[0] if context.resource_ids else None,
                context.action,
            )
            if cached is not None:
                return cached

        # Iterate evaluators
        candidate: AuthorizationDecision | None = None
        for evaluator in self._evaluators:
            decision = await evaluator.evaluate(principal, context)

            # Deny wins — short-circuit
            if decision.reason != "abstain" and not decision.allowed:
                await self._store_cache(principal, context, decision)
                return decision

            # First allow is the candidate
            if decision.allowed and candidate is None:
                candidate = decision

        result = candidate or AuthorizationDecision(
            allowed=False, reason="No evaluator granted access", evaluator="pep"
        )
        await self._store_cache(principal, context, result)
        return result

    async def evaluate_batch(
        self,
        principal: Principal,
        contexts: list[AuthorizationContext],
    ) -> list[AuthorizationDecision]:
        """Batch evaluation for multiple contexts."""
        return [await self.evaluate(principal, ctx) for ctx in contexts]

    async def _store_cache(
        self,
        principal: Principal,
        context: AuthorizationContext,
        decision: AuthorizationDecision,
    ) -> None:
        if self._cache is not None:
            await self._cache.set(
                principal.user_id,
                context.resource_type,
                context.resource_ids[0] if context.resource_ids else None,
                context.action,
                decision,
            )
