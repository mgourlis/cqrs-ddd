"""Tests for ABACConnector evaluator."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_access_control.evaluators.abac import ABACConnector
from cqrs_ddd_access_control.models import AuthorizationContext
from cqrs_ddd_identity import Principal, set_access_token
from cqrs_ddd_identity.context import _access_token_context


@pytest.fixture(autouse=True)
def _clean_context():
    yield
    _access_token_context.set(None)


class TestABACConnector:
    @pytest.mark.asyncio
    async def test_type_level_allowed(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")
        stub_auth_port.allowed_ids[("order", "read")] = ["type_level"]

        evaluator = ABACConnector(stub_auth_port)
        context = AuthorizationContext(
            resource_type="order",
            action="read",
            resource_ids=None,
        )
        decision = await evaluator.evaluate(principal, context)

        assert decision.allowed is True
        assert decision.evaluator == "abac"
        assert "type-level" in decision.reason

    @pytest.mark.asyncio
    async def test_type_level_denied(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")
        # No allowed_ids

        evaluator = ABACConnector(stub_auth_port)
        context = AuthorizationContext(
            resource_type="order",
            action="read",
            resource_ids=None,
        )
        decision = await evaluator.evaluate(principal, context)

        assert decision.allowed is False
        assert "denied type-level" in decision.reason

    @pytest.mark.asyncio
    async def test_resource_level_allowed(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")
        stub_auth_port.allowed_ids[("order", "read")] = ["o-1", "o-2"]

        evaluator = ABACConnector(stub_auth_port)
        context = AuthorizationContext(
            resource_type="order",
            action="read",
            resource_ids=["o-1", "o-2"],
        )
        decision = await evaluator.evaluate(principal, context)

        assert decision.allowed is True
        assert "granted" in decision.reason

    @pytest.mark.asyncio
    async def test_resource_level_partial_denied(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")
        stub_auth_port.allowed_ids[("order", "read")] = ["o-1"]
        # Requesting o-1 AND o-2, but only o-1 allowed

        evaluator = ABACConnector(stub_auth_port)
        context = AuthorizationContext(
            resource_type="order",
            action="read",
            resource_ids=["o-1", "o-2"],
        )
        decision = await evaluator.evaluate(principal, context)

        assert decision.allowed is False
        assert "denied" in decision.reason

    @pytest.mark.asyncio
    async def test_resource_level_all_denied(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")
        # No allowed_ids

        evaluator = ABACConnector(stub_auth_port)
        context = AuthorizationContext(
            resource_type="order",
            action="read",
            resource_ids=["o-1"],
        )
        decision = await evaluator.evaluate(principal, context)

        assert decision.allowed is False

    @pytest.mark.asyncio
    async def test_with_auth_context(
        self,
        principal: Principal,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")
        stub_auth_port.allowed_ids[("order", "read")] = ["o-1"]

        evaluator = ABACConnector(stub_auth_port)
        context = AuthorizationContext(
            resource_type="order",
            action="read",
            resource_ids=["o-1"],
            auth_context={"tenant_id": "t-1"},
        )
        decision = await evaluator.evaluate(principal, context)
        assert decision.allowed is True
