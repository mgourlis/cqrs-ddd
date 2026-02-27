"""Shared fixtures for specifications tests."""

from __future__ import annotations

import pytest

from cqrs_ddd_specifications.operators_memory import build_default_registry


@pytest.fixture
def registry():
    """Default in-memory operator registry for building specs."""
    return build_default_registry()
