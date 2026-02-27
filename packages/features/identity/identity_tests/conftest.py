"""Test configuration and fixtures."""

from __future__ import annotations

import pytest

from cqrs_ddd_identity import Principal
from cqrs_ddd_identity.session import InMemorySessionStore


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests that require external services",
    )


@pytest.fixture
def principal() -> Principal:
    """Create a test principal."""
    return Principal(
        user_id="test-user-123",
        username="testuser@example.com",
        roles=frozenset(["user", "admin"]),
        permissions=frozenset(["read:orders", "write:orders"]),
        claims={"email": "testuser@example.com", "name": "Test User"},
        tenant_id="test-tenant",
    )


@pytest.fixture
def anonymous_principal() -> Principal:
    """Create an anonymous principal."""
    return Principal.anonymous()


@pytest.fixture
def system_principal() -> Principal:
    """Create a system principal."""
    return Principal.system()


@pytest.fixture
def session_store() -> InMemorySessionStore:
    """Create an in-memory session store for testing."""
    return InMemorySessionStore()
