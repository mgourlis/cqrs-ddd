"""Shared fixtures for multitenancy integration tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from cqrs_ddd_multitenancy.context import (
    SYSTEM_TENANT,
    clear_tenant,
    reset_tenant,
    set_tenant,
)


@pytest.fixture(autouse=True)
def clear_tenant_context():
    """Clear tenant context before and after each test to prevent leakage."""
    clear_tenant()
    yield
    clear_tenant()


@pytest.fixture
def system_tenant_context():
    """Set the system tenant context for admin operations, reset after test."""
    token = set_tenant(SYSTEM_TENANT)
    yield SYSTEM_TENANT
    reset_tenant(token)


@pytest.fixture
def tmp_db_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for SQLite database files."""
    return tmp_path


@pytest.fixture
def sqlite_url_factory(tmp_db_dir: Path):
    """Factory that returns a SQLite URL for a given tenant ID."""

    def get_url(tenant_id: str) -> str:
        db_file = tmp_db_dir / f"{tenant_id}.db"
        return f"sqlite+aiosqlite:///{db_file}"

    return get_url
