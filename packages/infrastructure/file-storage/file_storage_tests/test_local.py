"""Tests for LocalBlobStorage adapter.

These are full integration tests that exercise real filesystem I/O
(in a temp directory) via aiofiles.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cqrs_ddd_file_storage.exceptions import BlobNotFoundError, PresignedUrlError
from cqrs_ddd_file_storage.local import LocalBlobStorage
from cqrs_ddd_file_storage.metadata import FileMetadata


@pytest.fixture
def storage(tmp_path: Path) -> LocalBlobStorage:
    return LocalBlobStorage(root=tmp_path, base_url="http://localhost:9000/blobs")


class TestLocalUpload:
    async def test_upload_bytes(
        self, storage: LocalBlobStorage, tmp_path: Path
    ) -> None:
        data = b"hello world"
        ref = await storage.upload("tenant/doc/1/hello.txt", data)
        assert ref.storage_backend == "local"
        assert ref.path == "tenant/doc/1/hello.txt"
        assert ref.metadata.size == len(data)
        assert ref.metadata.checksum == hashlib.sha256(data).hexdigest()
        assert (tmp_path / "tenant" / "doc" / "1" / "hello.txt").read_bytes() == data

    async def test_upload_stream(
        self, storage: LocalBlobStorage, tmp_path: Path
    ) -> None:
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

        async def stream():
            for c in chunks:
                yield c

        ref = await storage.upload("t/type/id/f.bin", stream())
        expected = b"".join(chunks)
        assert ref.metadata.size == len(expected)
        assert ref.metadata.checksum == hashlib.sha256(expected).hexdigest()
        assert (tmp_path / "t" / "type" / "id" / "f.bin").read_bytes() == expected

    async def test_upload_with_metadata(self, storage: LocalBlobStorage) -> None:
        meta = FileMetadata(content_type="image/png", custom_metadata={"tag": "avatar"})
        ref = await storage.upload("t/img/1/pic.png", b"\x89PNG", metadata=meta)
        assert ref.metadata.content_type == "image/png"
        assert ref.metadata.custom_metadata == {"tag": "avatar"}

    async def test_upload_creates_directories(
        self, storage: LocalBlobStorage, tmp_path: Path
    ) -> None:
        await storage.upload("a/b/c/deep.txt", b"deep")
        assert (tmp_path / "a" / "b" / "c" / "deep.txt").is_file()


class TestLocalDownload:
    async def test_download_existing(self, storage: LocalBlobStorage) -> None:
        data = b"download me"
        await storage.upload("t/d/1/f.txt", data)
        result = b""
        async for chunk in storage.download("t/d/1/f.txt"):
            result += chunk
        assert result == data

    async def test_download_not_found(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(BlobNotFoundError):
            await storage.download("no/such/path/f.txt")


class TestLocalDelete:
    async def test_delete_existing(
        self, storage: LocalBlobStorage, tmp_path: Path
    ) -> None:
        await storage.upload("t/d/1/f.txt", b"x")
        assert (tmp_path / "t" / "d" / "1" / "f.txt").is_file()
        await storage.delete("t/d/1/f.txt")
        assert not (tmp_path / "t" / "d" / "1" / "f.txt").exists()

    async def test_delete_missing_is_idempotent(
        self, storage: LocalBlobStorage
    ) -> None:
        await storage.delete("no/such/path/f.txt")  # should not raise


class TestLocalExists:
    async def test_exists_true(self, storage: LocalBlobStorage) -> None:
        await storage.upload("t/d/1/f.txt", b"x")
        assert await storage.exists("t/d/1/f.txt") is True

    async def test_exists_false(self, storage: LocalBlobStorage) -> None:
        assert await storage.exists("no/such/path/f.txt") is False


class TestLocalGetMetadata:
    async def test_get_metadata(self, storage: LocalBlobStorage) -> None:
        data = b"metadata test"
        await storage.upload("t/d/1/f.txt", data)
        meta = await storage.get_metadata("t/d/1/f.txt")
        assert meta.size == len(data)
        assert meta.checksum == hashlib.sha256(data).hexdigest()

    async def test_get_metadata_not_found(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(BlobNotFoundError):
            await storage.get_metadata("no/such/path/f.txt")


class TestLocalCopy:
    async def test_copy(self, storage: LocalBlobStorage, tmp_path: Path) -> None:
        data = b"copy me"
        await storage.upload("t/d/1/src.txt", data)
        ref = await storage.copy("t/d/1/src.txt", "t/d/1/dst.txt")
        assert ref.path == "t/d/1/dst.txt"
        assert ref.metadata.size == len(data)
        assert (tmp_path / "t" / "d" / "1" / "dst.txt").read_bytes() == data

    async def test_copy_not_found(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(BlobNotFoundError):
            await storage.copy("no/such/src.txt", "t/d/1/dst.txt")


class TestLocalPresignedUrl:
    async def test_get_url(self, storage: LocalBlobStorage) -> None:
        url = await storage.get_presigned_url(
            "t/d/1/f.txt", method="GET", expires_in=600
        )
        assert "http://localhost:9000/blobs/t/d/1/f.txt" in url
        assert "method=GET" in url
        assert "expires_in=600" in url

    async def test_put_url(self, storage: LocalBlobStorage) -> None:
        url = await storage.get_presigned_url("t/d/1/f.txt", method="PUT")
        assert "method=PUT" in url

    async def test_unsupported_method(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(PresignedUrlError):
            await storage.get_presigned_url("t/d/1/f.txt", method="DELETE")


class TestLocalListPrefix:
    async def test_list_prefix(self, storage: LocalBlobStorage) -> None:
        await storage.upload("t/d/1/a.txt", b"a")
        await storage.upload("t/d/1/b.txt", b"b")
        await storage.upload("t/other/1/c.txt", b"c")

        refs = []
        async for ref in storage.list_prefix("t/d"):
            refs.append(ref)
        assert len(refs) == 2
        paths = {r.path for r in refs}
        assert "t/d/1/a.txt" in paths
        assert "t/d/1/b.txt" in paths

    async def test_list_prefix_empty(self, storage: LocalBlobStorage) -> None:
        refs = []
        async for ref in storage.list_prefix("nonexistent/prefix"):
            refs.append(ref)
        assert len(refs) == 0
