"""Tests for exceptions module."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import InfrastructureError
from cqrs_ddd_file_storage.exceptions import (
    BlobNotFoundError,
    DownloadError,
    FileStorageError,
    PathTraversalError,
    PresignedUrlError,
    QuotaExceededError,
    UploadError,
)


class TestExceptionHierarchy:
    def test_file_storage_error_is_infrastructure_error(self) -> None:
        assert issubclass(FileStorageError, InfrastructureError)

    def test_blob_not_found_carries_path(self) -> None:
        err = BlobNotFoundError("tenant/invoice/1/file.pdf")
        assert err.path == "tenant/invoice/1/file.pdf"
        assert "Blob not found" in str(err)

    def test_quota_exceeded_carries_limits(self) -> None:
        err = QuotaExceededError("too big", limit=100, current=200)
        assert err.limit == 100
        assert err.current == 200

    def test_path_traversal_carries_path(self) -> None:
        err = PathTraversalError("../../etc/passwd")
        assert err.path == "../../etc/passwd"
        assert "traversal" in str(err).lower()

    def test_upload_error_is_file_storage_error(self) -> None:
        assert issubclass(UploadError, FileStorageError)

    def test_download_error_is_file_storage_error(self) -> None:
        assert issubclass(DownloadError, FileStorageError)

    def test_presigned_url_error_is_file_storage_error(self) -> None:
        assert issubclass(PresignedUrlError, FileStorageError)
