"""Base evaluator protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cqrs_ddd_identity import Principal

from ..models import AuthorizationContext, AuthorizationDecision


@runtime_checkable
class IPermissionEvaluator(Protocol):
    """Protocol for authorization evaluators composed by PEP.

    ``AuthorizationDecision`` with ``reason="abstain"`` signals no opinion.
    """

    async def evaluate(
        self,
        principal: Principal,
        context: AuthorizationContext,
    ) -> AuthorizationDecision:
        """Evaluate a single principal+context. Return allow/deny/abstain."""
        ...
