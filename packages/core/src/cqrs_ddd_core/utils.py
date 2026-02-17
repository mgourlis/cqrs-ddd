"""Common utility functions and helpers."""

from __future__ import annotations


def default_dict_factory() -> dict[str, object]:
    """Factory for mutable default dict in dataclass fields.

    Use this instead of dict() or {} to avoid dataclass default_factory issues.
    """
    return {}
