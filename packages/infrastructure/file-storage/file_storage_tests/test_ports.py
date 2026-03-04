"""Tests for IBlobStorage protocol."""

from __future__ import annotations

from collections.abc import AsyncIterator

from cqrs_ddd_file_storage.metadata import FileMetadata, StoredFileReference
from cqrs_ddd_file_storage.ports import IBlobStorage


class TestIBlobStorageProtocol:
    def test_protocol_is_runtime_checkable(self) -> None:
        class StubStorage:
            async def upload(
                self,
                path: str,
                data: bytes | AsyncIterator[bytes],
                metadata: FileMetadata | None = None,
            ) -> StoredFileReference:
                return StoredFileReference(path=path, metadata=FileMetadata())

            async def download(self, path: str) -> AsyncIterator[bytes]:
                yield b""

            async def delete(self, path: str) -> None:
                pass

            async def get_presigned_url(
                self,
                path: str,
                method: str = "GET",
                expires_in: int = 3600,
            ) -> str:
                return ""

            async def exists(self, path: str) -> bool:
                return False

            async def get_metadata(self, path: str) -> FileMetadata:
                return FileMetadata()

            async def copy(self, source: str, destination: str) -> StoredFileReference:
                return StoredFileReference(path=destination, metadata=FileMetadata())

            async def list_prefix(
                self, prefix: str
            ) -> AsyncIterator[StoredFileReference]:
                yield StoredFileReference(path="x", metadata=FileMetadata())

        assert isinstance(StubStorage(), IBlobStorage)

    def test_non_conforming_is_not_instance(self) -> None:
        class Empty:
            pass

        assert not isinstance(Empty(), IBlobStorage)
