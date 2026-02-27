"""Tests for request context."""

from __future__ import annotations

from cqrs_ddd_identity.request_context import (
    RequestContext,
    clear_request_context,
    get_client_ip,
    get_request_context,
    get_request_id,
    get_user_agent,
    reset_request_context,
    set_request_context,
)


class TestRequestContext:
    """Test RequestContext dataclass."""

    def test_creation_with_defaults(self) -> None:
        ctx = RequestContext()
        assert ctx.request_id is None
        assert ctx.ip_address is None
        assert ctx.user_agent is None
        assert ctx.path is None
        assert ctx.method is None
        assert ctx.created_at is not None

    def test_creation_with_values(self) -> None:
        ctx = RequestContext(
            request_id="req-1",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            path="/api/users",
            method="GET",
        )
        assert ctx.request_id == "req-1"
        assert ctx.ip_address == "192.168.1.1"
        assert ctx.user_agent == "Mozilla/5.0"
        assert ctx.path == "/api/users"
        assert ctx.method == "GET"

    def test_to_dict(self) -> None:
        ctx = RequestContext(
            request_id="r1",
            ip_address="10.0.0.1",
            path="/api",
            method="POST",
        )
        d = ctx.to_dict()
        assert d["request_id"] == "r1"
        assert d["ip_address"] == "10.0.0.1"
        assert d["path"] == "/api"
        assert d["method"] == "POST"
        assert "created_at" in d
        assert d["created_at"] is not None


class TestRequestContextContextVar:
    """Test get/set/reset/clear request context."""

    def test_get_request_context_when_not_set(self) -> None:
        clear_request_context()
        assert get_request_context() is None

    def test_set_and_get_request_context(self) -> None:
        ctx = RequestContext(request_id="abc", ip_address="1.2.3.4")
        token = set_request_context(ctx)
        try:
            assert get_request_context() == ctx
        finally:
            reset_request_context(token)

    def test_reset_request_context_restores_previous(self) -> None:
        clear_request_context()
        ctx1 = RequestContext(request_id="1")
        token1 = set_request_context(ctx1)
        ctx2 = RequestContext(request_id="2")
        token2 = set_request_context(ctx2)
        assert get_request_context() == ctx2
        reset_request_context(token2)
        assert get_request_context() == ctx1
        reset_request_context(token1)
        assert get_request_context() is None

    def test_clear_request_context(self) -> None:
        ctx = RequestContext(request_id="x")
        set_request_context(ctx)
        clear_request_context()
        assert get_request_context() is None


class TestRequestContextHelpers:
    """Test get_request_id, get_client_ip, get_user_agent."""

    def test_get_request_id_when_no_context(self) -> None:
        clear_request_context()
        assert get_request_id() is None

    def test_get_request_id_when_set(self) -> None:
        ctx = RequestContext(request_id="req-123")
        token = set_request_context(ctx)
        try:
            assert get_request_id() == "req-123"
        finally:
            reset_request_context(token)

    def test_get_client_ip_when_no_context(self) -> None:
        clear_request_context()
        assert get_client_ip() is None

    def test_get_client_ip_when_set(self) -> None:
        ctx = RequestContext(ip_address="10.0.0.5")
        token = set_request_context(ctx)
        try:
            assert get_client_ip() == "10.0.0.5"
        finally:
            reset_request_context(token)

    def test_get_user_agent_when_no_context(self) -> None:
        clear_request_context()
        assert get_user_agent() is None

    def test_get_user_agent_when_set(self) -> None:
        ctx = RequestContext(user_agent="CustomAgent/1.0")
        token = set_request_context(ctx)
        try:
            assert get_user_agent() == "CustomAgent/1.0"
        finally:
            reset_request_context(token)
