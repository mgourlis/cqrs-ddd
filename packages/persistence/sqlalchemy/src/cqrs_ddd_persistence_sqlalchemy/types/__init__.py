"""SQLAlchemy custom types.

Re-exports JSONType from core.types and conditionally SpatiaLite utilities.
"""

from __future__ import annotations

from ..core.types.json import JSONType

__all__ = ["JSONType"]
