"""Shared fixtures for file-storage tests."""

from __future__ import annotations

import pytest

from cqrs_ddd_file_storage.metadata import FileMetadata


@pytest.fixture
def sample_metadata() -> FileMetadata:
    """A sample ``FileMetadata`` with realistic values."""
    return FileMetadata(
        content_type="application/pdf",
        size=12345,
        checksum="abc123deadbeef",
        custom_metadata={"author": "test"},
    )


@pytest.fixture
def sample_bytes() -> bytes:
    """Some bytes for upload tests."""
    return b"Hello, blob storage!" * 100
