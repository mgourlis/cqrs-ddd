"""cqrs-ddd-file-storage — Blob management for the CQRS/DDD toolkit."""

from __future__ import annotations

from .exceptions import (
    BlobNotFoundError,
    DownloadError,
    FileStorageError,
    PathTraversalError,
    PresignedUrlError,
    QuotaExceededError,
    UploadError,
)
from .metadata import FileMetadata, StoredFileReference
from .path import BlobPath, validate_path
from .ports import IBlobStorage
from .virus_scan import IVirusScanner, ScanResult, ScanVerdict

__all__ = [
    # Ports
    "IBlobStorage",
    "IVirusScanner",
    # Value objects
    "FileMetadata",
    "StoredFileReference",
    "BlobPath",
    "ScanResult",
    "ScanVerdict",
    # Utilities
    "validate_path",
    # Exceptions
    "FileStorageError",
    "BlobNotFoundError",
    "QuotaExceededError",
    "PathTraversalError",
    "UploadError",
    "DownloadError",
    "PresignedUrlError",
]
