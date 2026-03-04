"""Structured blob path builder with tenant isolation and traversal protection."""

from __future__ import annotations

import posixpath
import re

from .exceptions import PathTraversalError

# Pattern that catches ``..``, leading ``/``, or any backslash.
_UNSAFE_SEGMENT = re.compile(r"(^|/)\.\.(/|$)|\\")
_ABSOLUTE_PATH = re.compile(r"^/")


def _validate_segment(value: str, name: str) -> str:
    """Validate a single path segment (no slashes, no traversal, non-empty)."""
    if not value:
        msg = f"{name} must be a non-empty string"
        raise ValueError(msg)
    if "/" in value or "\\" in value:
        msg = f"{name} must not contain path separators: {value!r}"
        raise ValueError(msg)
    if value in (".", ".."):
        msg = f"{name} must not be '.' or '..': {value!r}"
        raise PathTraversalError(value)
    return value


def validate_path(path: str) -> str:
    """Validate that *path* contains no traversal sequences.

    Returns the normalised (POSIX) path on success.
    Raises :class:`PathTraversalError` on ``../``, absolute paths,
    or backslash separators.
    """
    if not path:
        msg = "Path must be a non-empty string"
        raise ValueError(msg)
    if _ABSOLUTE_PATH.match(path):
        raise PathTraversalError(path)
    if _UNSAFE_SEGMENT.search(path):
        raise PathTraversalError(path)
    normalised = posixpath.normpath(path)
    if normalised.startswith(".."):
        raise PathTraversalError(path)
    return normalised


class BlobPath:
    """Structured path builder enforcing tenant-scoped directory layout.

    The canonical form is::

        {tenant_id}/{entity_type}/{entity_id}/{filename}

    Every segment is validated against path-traversal attacks.
    """

    __slots__ = ("_tenant_id", "_entity_type", "_entity_id", "_filename")

    def __init__(
        self,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        filename: str,
    ) -> None:
        self._tenant_id = _validate_segment(tenant_id, "tenant_id")
        self._entity_type = _validate_segment(entity_type, "entity_type")
        self._entity_id = _validate_segment(entity_id, "entity_id")
        self._filename = _validate_segment(filename, "filename")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        filename: str,
    ) -> str:
        """Build and return the canonical path string.

        Example::

            BlobPath.build("t1", "invoice", "inv-123", "scan.pdf")
            # → "t1/invoice/inv-123/scan.pdf"
        """
        return str(cls(tenant_id, entity_type, entity_id, filename))

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def entity_type(self) -> str:
        return self._entity_type

    @property
    def entity_id(self) -> str:
        return self._entity_id

    @property
    def filename(self) -> str:
        return self._filename

    def __str__(self) -> str:
        return (
            f"{self._tenant_id}/{self._entity_type}/{self._entity_id}/{self._filename}"
        )

    def __repr__(self) -> str:
        return (
            f"BlobPath(tenant_id={self._tenant_id!r}, "
            f"entity_type={self._entity_type!r}, entity_id={self._entity_id!r}, "
            f"filename={self._filename!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BlobPath):
            return NotImplemented
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))
