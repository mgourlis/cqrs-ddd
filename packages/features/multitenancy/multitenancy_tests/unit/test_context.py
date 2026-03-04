"""Tests for tenant context management."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from cqrs_ddd_multitenancy.context import (
    SYSTEM_TENANT,
    clear_tenant,
    get_current_tenant,
    get_current_tenant_or_none,
    get_tenant_context_vars,
    is_system_tenant,
    is_tenant_context_set,
    propagate_tenant_context,
    require_tenant,
    reset_tenant,
    run_in_tenant_context,
    set_tenant,
    system_operation,
    with_tenant_context,
)
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError


class TestTenantContextBasics:
    """Tests for basic tenant context operations."""

    def setup_method(self) -> None:
        """Clear tenant context before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant context after each test."""
        clear_tenant()

    def test_initial_state_is_none(self) -> None:
        """Test that initial tenant context is None."""
        assert get_current_tenant_or_none() is None
        assert not is_tenant_context_set()

    def test_set_and_get_tenant(self) -> None:
        """Test setting and getting tenant context."""
        token = set_tenant("tenant-123")
        assert get_current_tenant() == "tenant-123"
        assert get_current_tenant_or_none() == "tenant-123"
        assert is_tenant_context_set()
        reset_tenant(token)

    def test_get_current_tenant_raises_when_not_set(self) -> None:
        """Test that get_current_tenant raises when no context."""
        with pytest.raises(TenantContextMissingError):
            get_current_tenant()

    def test_clear_tenant(self) -> None:
        """Test clearing tenant context."""
        set_tenant("tenant-123")
        assert get_current_tenant_or_none() == "tenant-123"

        clear_tenant()
        assert get_current_tenant_or_none() is None

    def test_set_empty_tenant_raises(self) -> None:
        """Test that setting empty tenant raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            set_tenant("")

    def test_require_tenant(self) -> None:
        """Test require_tenant function."""
        with pytest.raises(TenantContextMissingError):
            require_tenant()

        token = set_tenant("tenant-123")
        assert require_tenant() == "tenant-123"
        reset_tenant(token)


class TestSystemTenant:
    """Tests for system tenant functionality."""

    def setup_method(self) -> None:
        """Clear tenant context before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant context after each test."""
        clear_tenant()

    def test_system_tenant_constant(self) -> None:
        """Test SYSTEM_TENANT constant."""
        assert SYSTEM_TENANT == "__system__"

    def test_is_system_tenant_true(self) -> None:
        """Test is_system_tenant returns True for system tenant."""
        token = set_tenant(SYSTEM_TENANT)
        assert is_system_tenant() is True
        reset_tenant(token)

    def test_is_system_tenant_false(self) -> None:
        """Test is_system_tenant returns False for regular tenant."""
        token = set_tenant("tenant-123")
        assert is_system_tenant() is False
        reset_tenant(token)

    def test_is_system_tenant_false_when_none(self) -> None:
        """Test is_system_tenant returns False when no tenant."""
        assert is_system_tenant() is False


class TestTokenReset:
    """Tests for token-based context reset."""

    def setup_method(self) -> None:
        """Clear tenant context before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant context after each test."""
        clear_tenant()

    def test_token_reset_restores_previous(self) -> None:
        """Test that token reset restores previous context."""
        # No initial context
        assert get_current_tenant_or_none() is None

        # Set first tenant
        token1 = set_tenant("tenant-1")
        assert get_current_tenant() == "tenant-1"

        # Set second tenant
        token2 = set_tenant("tenant-2")
        assert get_current_tenant() == "tenant-2"

        # Reset to first
        reset_tenant(token2)
        assert get_current_tenant() == "tenant-1"

        # Reset to None
        reset_tenant(token1)
        assert get_current_tenant_or_none() is None

    def test_nested_context_with_tokens(self) -> None:
        """Test nested context with proper token management."""
        token1 = set_tenant("outer")
        assert get_current_tenant() == "outer"

        token2 = set_tenant("inner")
        assert get_current_tenant() == "inner"

        reset_tenant(token2)
        assert get_current_tenant() == "outer"

        reset_tenant(token1)
        assert get_current_tenant_or_none() is None


class TestSystemOperationDecorator:
    """Tests for @system_operation decorator."""

    def setup_method(self) -> None:
        """Clear tenant context before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant context after each test."""
        clear_tenant()

    @pytest.mark.asyncio
    async def test_system_operation_sets_system_tenant(self) -> None:
        """Test that @system_operation sets SYSTEM_TENANT."""

        @system_operation
        async def admin_func() -> str:
            assert is_system_tenant() is True
            return get_current_tenant()

        result = await admin_func()
        assert result == SYSTEM_TENANT

    @pytest.mark.asyncio
    async def test_system_operation_resets_after(self) -> None:
        """Test that @system_operation resets context after."""

        @system_operation
        async def admin_func() -> None:
            pass

        # No context before
        assert get_current_tenant_or_none() is None

        await admin_func()

        # No context after
        assert get_current_tenant_or_none() is None

    @pytest.mark.asyncio
    async def test_system_operation_preserves_existing_context(self) -> None:
        """Test that @system_operation preserves and restores existing context."""
        token = set_tenant("tenant-123")

        @system_operation
        async def admin_func() -> None:
            assert is_system_tenant() is True

        await admin_func()

        # Restored to original
        assert get_current_tenant() == "tenant-123"
        reset_tenant(token)


class TestTenantContextManager:
    """Tests for with_tenant_context context manager."""

    def setup_method(self) -> None:
        """Clear tenant context before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant context after each test."""
        clear_tenant()

    @pytest.mark.asyncio
    async def test_context_manager_sets_tenant(self) -> None:
        """Test that context manager sets tenant."""
        async with with_tenant_context("tenant-123") as tenant_id:
            assert tenant_id == "tenant-123"
            assert get_current_tenant() == "tenant-123"

        assert get_current_tenant_or_none() is None

    @pytest.mark.asyncio
    async def test_context_manager_nesting(self) -> None:
        """Test nested context managers."""
        async with with_tenant_context("outer"):
            assert get_current_tenant() == "outer"

            async with with_tenant_context("inner"):
                assert get_current_tenant() == "inner"

            assert get_current_tenant() == "outer"

        assert get_current_tenant_or_none() is None


class TestPropagateTenantContext:
    """Tests for propagate_tenant_context function."""

    def setup_method(self) -> None:
        """Clear tenant context before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant context after each test."""
        clear_tenant()

    @pytest.mark.asyncio
    async def test_propagate_captures_current_context(self) -> None:
        """Test that propagate_tenant_context captures current context."""
        token = set_tenant("tenant-123")

        async def background_task() -> str:
            return get_current_tenant()

        wrapped = propagate_tenant_context(background_task)

        # Clear context
        reset_tenant(token)
        assert get_current_tenant_or_none() is None

        # Wrapped function has captured context
        result = await wrapped()
        assert result == "tenant-123"

    @pytest.mark.asyncio
    async def test_propagate_with_explicit_tenant(self) -> None:
        """Test propagate_tenant_context with explicit tenant."""

        async def task() -> str:
            return get_current_tenant()

        wrapped = propagate_tenant_context(task, tenant_id="explicit-tenant")

        result = await wrapped()
        assert result == "explicit-tenant"


class TestGetTenantContextVars:
    """Tests for get_tenant_context_vars function."""

    def setup_method(self) -> None:
        """Clear tenant context before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant context after each test."""
        clear_tenant()

    def test_returns_dict_with_tenant_id(self) -> None:
        """Test that get_tenant_context_vars returns tenant_id."""
        token = set_tenant("tenant-123")
        ctx = get_tenant_context_vars()
        assert ctx == {"tenant_id": "tenant-123"}
        reset_tenant(token)

    def test_returns_none_when_no_context(self) -> None:
        """Test that get_tenant_context_vars returns None when no context."""
        ctx = get_tenant_context_vars()
        assert ctx == {"tenant_id": None}


class TestRunInTenantContext:
    """Tests for run_in_tenant_context function."""

    def setup_method(self) -> None:
        """Clear tenant context before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant context after each test."""
        clear_tenant()

    def test_runs_sync_function_with_tenant(self) -> None:
        """Test running sync function in tenant context."""

        def get_tenant() -> str | None:
            return get_current_tenant_or_none()

        result = run_in_tenant_context("tenant-123", get_tenant)
        assert result == "tenant-123"

    def test_isolates_context(self) -> None:
        """Test that context is isolated."""

        def get_tenant() -> str | None:
            return get_current_tenant_or_none()

        # Run in isolated context
        result = run_in_tenant_context("isolated", get_tenant)
        assert result == "isolated"

        # Main context is still None
        assert get_current_tenant_or_none() is None


class TestAsyncIsolation:
    """Tests for async context isolation."""

    def setup_method(self) -> None:
        """Clear tenant context before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant context after each test."""
        clear_tenant()

    @pytest.mark.asyncio
    async def test_async_tasks_isolated(self) -> None:
        """Test that async tasks have isolated context."""
        results: dict[str, str | None] = {}

        async def task(tenant_id: str) -> None:
            token = set_tenant(tenant_id)
            await asyncio.sleep(0.01)  # Simulate async work
            results[tenant_id] = get_current_tenant_or_none()
            reset_tenant(token)

        # Run multiple tasks concurrently
        await asyncio.gather(
            task("tenant-1"),
            task("tenant-2"),
            task("tenant-3"),
        )

        # Each task saw its own tenant
        assert results["tenant-1"] == "tenant-1"
        assert results["tenant-2"] == "tenant-2"
        assert results["tenant-3"] == "tenant-3"
