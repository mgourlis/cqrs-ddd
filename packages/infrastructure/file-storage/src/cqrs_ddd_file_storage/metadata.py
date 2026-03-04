"""Immutable value objects for file metadata and stored references."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class FileMetadata:
    """Immutable value object describing a blob's metadata.

    Attributes:
        content_type: MIME type (e.g. ``"application/pdf"``).
        size: File size in bytes (``None`` if unknown before upload).
        checksum: SHA-256 hex digest (``None`` if not yet computed).
        created_at: Timestamp of creation / upload.
        custom_metadata: Provider-agnostic key/value metadata.
    """

    content_type: str = "application/octet-stream"
    size: int | None = None
    checksum: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    custom_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StoredFileReference:
    """Immutable value object returned after a successful upload or copy.

    Attributes:
        path: Canonical storage path (e.g. ``"t1/invoice/inv-1/scan.pdf"``).
        metadata: Metadata of the stored blob.
        storage_backend: Identifier for multi-backend routing
                         (e.g. ``"s3"``, ``"azure"``, ``"local"``).
    """

    path: str
    metadata: FileMetadata
    storage_backend: str = ""
