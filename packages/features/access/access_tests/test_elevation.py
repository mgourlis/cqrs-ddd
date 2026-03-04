"""Tests for verify_elevation."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_access_control.elevation import verify_elevation
from cqrs_ddd_access_control.exceptions import ElevationRequiredError
from cqrs_ddd_identity import set_access_token
from cqrs_ddd_identity.context import _access_token_context


@pytest.fixture(autouse=True)
def _clean_context():
    yield
    _access_token_context.set(None)


class TestVerifyElevation:
    @pytest.mark.asyncio
    async def test_elevated_returns_true(
        self,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")
        stub_auth_port.allowed_ids[("elevation", "delete_tenant")] = ["allowed"]

        result = await verify_elevation(stub_auth_port, "delete_tenant")
        assert result is True

    @pytest.mark.asyncio
    async def test_not_elevated_raises(
        self,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")
        # No allowed_ids for elevation

        with pytest.raises(ElevationRequiredError):
            await verify_elevation(stub_auth_port, "delete_tenant")

    @pytest.mark.asyncio
    async def test_not_elevated_return_mode(
        self,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")

        result = await verify_elevation(
            stub_auth_port,
            "delete_tenant",
            on_fail="return",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_default_on_fail_is_raise(
        self,
        stub_auth_port: Any,
    ) -> None:
        set_access_token("tok")

        with pytest.raises(ElevationRequiredError):
            await verify_elevation(stub_auth_port, "some_action")

    @pytest.mark.asyncio
    async def test_no_access_token(
        self,
        stub_auth_port: Any,
    ) -> None:
        _access_token_context.set(None)

        result = await verify_elevation(
            stub_auth_port,
            "something",
            on_fail="return",
        )
        assert result is False
