"""Local filesystem adapter for :class:`IBlobStorage`.

Uses ``aiofiles`` for non-blocking I/O.  Intended for **development only** —
not for production workloads.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

from .exceptions import BlobNotFoundError, PresignedUrlError, UploadError
from .metadata import FileMetadata, StoredFileReference
from .path import validate_path
from .ports import IBlobStorage

_CHUNK_SIZE = 64 * 1024  # 64 KiB


class LocalBlobStorage(IBlobStorage):
    """Filesystem-backed blob storage for local development.

    Parameters:
        root: Root directory in which blobs are stored.
        base_url: Base URL returned by :meth:`get_presigned_url`.
                  Defaults to ``http://localhost:8000/dev/blobs``.
    """

    def __init__(
        self, root: str | Path, *, base_url: str = "http://localhost:8000/dev/blobs"
    ) -> None:
        self._root = Path(root)
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # IBlobStorage implementation
    # ------------------------------------------------------------------

    async def upload(
        self,
        path: str,
        data: bytes | AsyncIterator[bytes],
        metadata: FileMetadata | None = None,
    ) -> StoredFileReference:
        import aiofiles  # type: ignore[import-untyped]

        safe = validate_path(path)
        target = self._root / safe
        target.parent.mkdir(parents=True, exist_ok=True)

        sha = hashlib.sha256()
        size = 0

        try:
            async with aiofiles.open(target, "wb") as fh:
                if isinstance(data, bytes):
                    await fh.write(data)
                    sha.update(data)
                    size = len(data)
                else:
                    async for chunk in data:
                        await fh.write(chunk)
                        sha.update(chunk)
                        size += len(chunk)
        except OSError as exc:
            raise UploadError(f"Failed to write {safe}: {exc}") from exc

        meta = FileMetadata(
            content_type=metadata.content_type
            if metadata
            else "application/octet-stream",
            size=size,
            checksum=sha.hexdigest(),
            created_at=metadata.created_at if metadata else datetime.now(timezone.utc),
            custom_metadata=dict(metadata.custom_metadata) if metadata else {},
        )
        return StoredFileReference(path=safe, metadata=meta, storage_backend="local")

    def download(self, path: str) -> AsyncIterator[bytes]:
        safe = validate_path(path)
        target = self._root / safe
        if not target.is_file():
            raise BlobNotFoundError(safe)
        return self._stream_file(target)

    async def delete(self, path: str) -> None:
        safe = validate_path(path)
        target = self._root / safe
        with contextlib.suppress(OSError):
            target.unlink(missing_ok=True)

    async def get_presigned_url(
        self,
        path: str,
        method: str = "GET",
        expires_in: int = 3600,
    ) -> str:
        safe = validate_path(path)
        if method.upper() not in ("GET", "PUT"):
            raise PresignedUrlError(
                f"Unsupported method for local presigned URL: {method}"
            )
        return (
            f"{self._base_url}/{safe}?method={method.upper()}&expires_in={expires_in}"
        )

    async def exists(self, path: str) -> bool:
        safe = validate_path(path)
        return (self._root / safe).is_file()

    async def get_metadata(self, path: str) -> FileMetadata:
        import aiofiles

        safe = validate_path(path)
        target = self._root / safe
        if not target.is_file():
            raise BlobNotFoundError(safe)

        stat = target.stat()
        sha = hashlib.sha256()
        async with aiofiles.open(target, "rb") as fh:
            while True:
                chunk = await fh.read(_CHUNK_SIZE)
                if not chunk:
                    break
                sha.update(chunk)

        return FileMetadata(
            size=stat.st_size,
            checksum=sha.hexdigest(),
            created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
        )

    async def copy(self, source: str, destination: str) -> StoredFileReference:
        import aiofiles

        src_safe = validate_path(source)
        dst_safe = validate_path(destination)
        src = self._root / src_safe
        dst = self._root / dst_safe

        if not src.is_file():
            raise BlobNotFoundError(src_safe)

        dst.parent.mkdir(parents=True, exist_ok=True)

        sha = hashlib.sha256()
        size = 0
        async with (
            aiofiles.open(src, "rb") as reader,
            aiofiles.open(dst, "wb") as writer,
        ):
            while True:
                chunk = await reader.read(_CHUNK_SIZE)
                if not chunk:
                    break
                await writer.write(chunk)
                sha.update(chunk)
                size += len(chunk)

        meta = FileMetadata(
            size=size,
            checksum=sha.hexdigest(),
            created_at=datetime.now(timezone.utc),
        )
        return StoredFileReference(
            path=dst_safe, metadata=meta, storage_backend="local"
        )

    def list_prefix(self, prefix: str) -> AsyncIterator[StoredFileReference]:
        safe = validate_path(prefix) if prefix else ""
        base = self._root / safe if safe else self._root
        return self._iter_prefix(base, safe)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _stream_file(target: Path) -> AsyncIterator[bytes]:
        import aiofiles

        async with aiofiles.open(target, "rb") as fh:
            while True:
                chunk = await fh.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    async def _iter_prefix(
        self, base: Path, _prefix: str
    ) -> AsyncIterator[StoredFileReference]:
        if not base.exists():
            return
        for root_str, _dirs, files in os.walk(base):
            root_path = Path(root_str)
            for name in sorted(files):
                file_path = root_path / name
                rel = file_path.relative_to(self._root).as_posix()
                stat = file_path.stat()
                meta = FileMetadata(
                    size=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
                )
                yield StoredFileReference(
                    path=rel, metadata=meta, storage_backend="local"
                )
