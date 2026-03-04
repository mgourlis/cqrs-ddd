"""Pytest configuration for multitenancy tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_tenant_context() -> None:
    """Automatically clear tenant context before and after each test."""
    from cqrs_ddd_multitenancy.context import clear_tenant

    clear_tenant()
    yield
    clear_tenant()
