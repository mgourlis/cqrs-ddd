"""Pytest fixtures for messaging tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the messaging package is importable when running pytest from repo root
# (e.g. without pip install -e ./packages/infrastructure/messaging)
_messaging_src = Path(__file__).resolve().parent.parent / "src"
if _messaging_src.is_dir() and str(_messaging_src) not in sys.path:
    sys.path.insert(0, str(_messaging_src))


@pytest.fixture(scope="session")
def rabbitmq_url() -> str:
    """Override in integration tests with testcontainers."""
    return "amqp://guest:guest@localhost/"


@pytest.fixture(scope="session")
def kafka_bootstrap_servers() -> str:
    """Override in integration tests with testcontainers."""
    return "localhost:9092"
