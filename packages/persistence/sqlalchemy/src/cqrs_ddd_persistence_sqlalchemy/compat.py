"""Compatibility utilities for soft dependencies."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import cqrs_ddd_advanced_core  # noqa: F401

    HAS_ADVANCED = True
except ImportError:
    HAS_ADVANCED = False


def require_advanced(feature_name: str) -> None:
    """
    Guard for features that require cqrs-ddd-advanced-core.

    Args:
        feature_name: The name of the feature being accessed.

    Raises:
        ImportError: If advanced-core is not installed.
    """
    if not HAS_ADVANCED:
        raise ImportError(
            f"{feature_name} requires 'cqrs-ddd-advanced-core'. "
            "Install it via 'pip install cqrs-ddd-persistence-sqlalchemy[advanced]'"
        )
