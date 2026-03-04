"""File-storage-specific exceptions for cqrs-ddd-file-storage."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import InfrastructureError


class FileStorageError(InfrastructureError):
    """Base class for all file-storage-related infrastructure errors."""


class BlobNotFoundError(FileStorageError):
    """Raised when a requested blob does not exist at the given path."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Blob not found: {path}")


class QuotaExceededError(FileStorageError):
    """Raised when a storage quota or size limit is exceeded."""

    def __init__(
        self, message: str, *, limit: int | None = None, current: int | None = None
    ) -> None:
        self.limit = limit
        self.current = current
        super().__init__(message)


class PathTraversalError(FileStorageError):
    """Raised when a path contains traversal sequences (e.g. ``../``)."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Path traversal detected: {path!r}")


class UploadError(FileStorageError):
    """Raised when an upload operation fails."""


class DownloadError(FileStorageError):
    """Raised when a download / streaming read fails."""


class PresignedUrlError(FileStorageError):
    """Raised when presigned / signed URL generation fails."""
