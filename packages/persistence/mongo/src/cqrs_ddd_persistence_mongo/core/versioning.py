"""Shared helpers for optimistic locking (version field) on MongoDB documents."""

from __future__ import annotations

from typing import Any


def check_document_version(doc: dict[str, Any], expected_version: int) -> None:
    """
    Verify document version matches expected version.

    Args:
        doc: MongoDB document dictionary
        expected_version: Expected version number

    Raises:
        OptimisticConcurrencyError: If versions don't match
    """
    from cqrs_ddd_core.primitives.exceptions import OptimisticConcurrencyError

    actual_version = doc.get("version", 0)
    if actual_version != expected_version:
        raise OptimisticConcurrencyError(
            f"Concurrent modification detected: expected version {expected_version}, "
            f"but document has version {actual_version}"
        )


def increment_document_version(doc: dict[str, Any]) -> int:
    """
    Increment and return new version number.

    Args:
        doc: MongoDB document dictionary

    Returns:
        New version number (old_version + 1)
    """
    new_version = doc.get("version", 0) + 1
    doc["version"] = new_version
    return new_version


def document_has_version(doc: dict[str, Any]) -> bool:
    """Check if document has a version field."""
    return "version" in doc
