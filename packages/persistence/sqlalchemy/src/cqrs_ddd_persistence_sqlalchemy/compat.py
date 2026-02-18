"""Compatibility utilities for soft dependencies."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import cqrs_ddd_advanced_core  # noqa: F401

    HAS_ADVANCED = True
except ImportError:
    HAS_ADVANCED = False

try:
    import geoalchemy2  # noqa: F401

    HAS_GEOMETRY = True
except ImportError:
    HAS_GEOMETRY = False

try:
    import pydantic_shapely  # noqa: F401

    HAS_PYDANTIC_SHAPELY = True
except ImportError:
    HAS_PYDANTIC_SHAPELY = False


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


def require_geometry(feature_name: str) -> None:
    """
    Guard for features that require geoalchemy2 (geometry extra).

    Args:
        feature_name: The name of the feature being accessed.

    Raises:
        ImportError: If geometry dependencies are not installed.
    """
    if not HAS_GEOMETRY:
        raise ImportError(
            f"{feature_name} requires 'geoalchemy2'. "
            "Install it via 'pip install cqrs-ddd-persistence-sqlalchemy[geometry]'"
        )
