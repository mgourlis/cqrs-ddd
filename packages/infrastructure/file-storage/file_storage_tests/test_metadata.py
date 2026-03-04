"""Tests for FileMetadata and StoredFileReference."""

from __future__ import annotations

from datetime import datetime, timezone

from cqrs_ddd_file_storage.metadata import FileMetadata, StoredFileReference


class TestFileMetadata:
    def test_default_content_type(self) -> None:
        meta = FileMetadata()
        assert meta.content_type == "application/octet-stream"

    def test_immutable(self) -> None:
        meta = FileMetadata(content_type="text/plain", size=42)
        import pytest

        with pytest.raises(AttributeError):
            meta.size = 99  # type: ignore[misc]

    def test_custom_metadata(self) -> None:
        meta = FileMetadata(custom_metadata={"owner": "alice"})
        assert meta.custom_metadata["owner"] == "alice"

    def test_created_at_defaults_to_utc(self) -> None:
        meta = FileMetadata()
        assert meta.created_at.tzinfo is not None

    def test_explicit_values(self) -> None:
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        meta = FileMetadata(
            content_type="image/png",
            size=1024,
            checksum="sha256hash",
            created_at=ts,
        )
        assert meta.content_type == "image/png"
        assert meta.size == 1024
        assert meta.checksum == "sha256hash"
        assert meta.created_at == ts


class TestStoredFileReference:
    def test_basic(self) -> None:
        meta = FileMetadata(size=100)
        ref = StoredFileReference(
            path="t1/doc/1/f.pdf", metadata=meta, storage_backend="s3"
        )
        assert ref.path == "t1/doc/1/f.pdf"
        assert ref.storage_backend == "s3"
        assert ref.metadata.size == 100

    def test_default_backend(self) -> None:
        ref = StoredFileReference(path="p", metadata=FileMetadata())
        assert ref.storage_backend == ""

    def test_immutable(self) -> None:
        ref = StoredFileReference(path="p", metadata=FileMetadata())
        import pytest

        with pytest.raises(AttributeError):
            ref.path = "other"  # type: ignore[misc]
