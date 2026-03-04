"""Port definition (protocol) for blob storage."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from .metadata import FileMetadata, StoredFileReference


@runtime_checkable
class IBlobStorage(Protocol):
    """Framework-agnostic protocol for blob / file storage.

    Adapters must explicitly declare ``class Foo(IBlobStorage):`` and
    implement every method.  Domain and application layers depend only
    on this protocol — never on provider SDKs directly.
    """

    async def upload(
        self,
        path: str,
        data: bytes | AsyncIterator[bytes],
        metadata: FileMetadata | None = None,
    ) -> StoredFileReference:
        """Upload a blob to *path*.

        *data* may be raw ``bytes`` (small files) or an
        ``AsyncIterator[bytes]`` for memory-safe streaming.
        """
        ...

    def download(self, path: str) -> AsyncIterator[bytes]:
        """Stream blob contents as an async iterator of chunks."""
        ...

    async def delete(self, path: str) -> None:
        """Delete the blob at *path*.  Must not raise if already absent."""
        ...

    async def get_presigned_url(
        self,
        path: str,
        method: str = "GET",
        expires_in: int = 3600,
    ) -> str:
        """Return a time-limited URL for direct client access.

        *method* controls the allowed HTTP verb (``GET`` or ``PUT``).
        *expires_in* is the validity window in seconds.
        """
        ...

    async def exists(self, path: str) -> bool:
        """Return ``True`` if a blob exists at *path*."""
        ...

    async def get_metadata(self, path: str) -> FileMetadata:
        """Retrieve metadata for the blob at *path*."""
        ...

    async def copy(self, source: str, destination: str) -> StoredFileReference:
        """Copy a blob from *source* to *destination*."""
        ...

    def list_prefix(self, prefix: str) -> AsyncIterator[StoredFileReference]:
        """List all blobs whose path starts with *prefix*."""
        ...
