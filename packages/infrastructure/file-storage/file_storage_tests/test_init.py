"""Tests for the public __init__ exports."""

from __future__ import annotations

import cqrs_ddd_file_storage


class TestPublicAPI:
    def test_exports_ports(self) -> None:
        assert hasattr(cqrs_ddd_file_storage, "IBlobStorage")
        assert hasattr(cqrs_ddd_file_storage, "IVirusScanner")

    def test_exports_value_objects(self) -> None:
        assert hasattr(cqrs_ddd_file_storage, "FileMetadata")
        assert hasattr(cqrs_ddd_file_storage, "StoredFileReference")
        assert hasattr(cqrs_ddd_file_storage, "BlobPath")
        assert hasattr(cqrs_ddd_file_storage, "ScanResult")
        assert hasattr(cqrs_ddd_file_storage, "ScanVerdict")

    def test_exports_utilities(self) -> None:
        assert hasattr(cqrs_ddd_file_storage, "validate_path")

    def test_exports_exceptions(self) -> None:
        assert hasattr(cqrs_ddd_file_storage, "FileStorageError")
        assert hasattr(cqrs_ddd_file_storage, "BlobNotFoundError")
        assert hasattr(cqrs_ddd_file_storage, "QuotaExceededError")
        assert hasattr(cqrs_ddd_file_storage, "PathTraversalError")
        assert hasattr(cqrs_ddd_file_storage, "UploadError")
        assert hasattr(cqrs_ddd_file_storage, "DownloadError")
        assert hasattr(cqrs_ddd_file_storage, "PresignedUrlError")

    def test_all_members_in_dunder_all(self) -> None:
        for name in cqrs_ddd_file_storage.__all__:
            assert hasattr(cqrs_ddd_file_storage, name), f"{name} missing from module"
