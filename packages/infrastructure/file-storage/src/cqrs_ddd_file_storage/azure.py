"""Azure Blob Storage adapter for :class:`IBlobStorage`.

Requires the ``[azure]`` extra (``azure-storage-blob[aio]>=12.19.0``).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

from .exceptions import (
    BlobNotFoundError,
    DownloadError,
    PresignedUrlError,
    UploadError,
)
from .metadata import FileMetadata, StoredFileReference
from .path import validate_path
from .ports import IBlobStorage

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB


class AzureBlobStorage(IBlobStorage):
    """Azure Blob Storage adapter with SAS token support.

    Parameters:
        connection_string: Azure Storage connection string.
        container_name: Blob container name.
        account_name: Storage account name (needed for SAS URL generation).
        account_key: Storage account key (needed for SAS URL generation).
        prefix: Optional path prefix applied to all blob names.
    """

    def __init__(
        self,
        connection_string: str,
        container_name: str,
        *,
        account_name: str = "",
        account_key: str = "",
        prefix: str = "",
    ) -> None:
        self._connection_string = connection_string
        self._container_name = container_name
        self._account_name = account_name
        self._account_key = account_key
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""

    def _blob_name(self, path: str) -> str:
        return f"{self._prefix}{validate_path(path)}"

    def _get_container_client(self) -> Any:
        from azure.storage.blob.aio import (
            BlobServiceClient,
        )

        service = BlobServiceClient.from_connection_string(self._connection_string)
        return service.get_container_client(self._container_name)

    # ------------------------------------------------------------------
    # IBlobStorage
    # ------------------------------------------------------------------

    async def upload(
        self,
        path: str,
        data: bytes | AsyncIterator[bytes],
        metadata: FileMetadata | None = None,
    ) -> StoredFileReference:
        blob_name = self._blob_name(path)
        container = self._get_container_client()

        content_type = metadata.content_type if metadata else "application/octet-stream"
        custom_meta = (
            dict(metadata.custom_metadata)
            if metadata and metadata.custom_metadata
            else {}
        )

        try:
            async with container:
                blob = container.get_blob_client(blob_name)
                if isinstance(data, bytes):
                    await blob.upload_blob(
                        data,
                        overwrite=True,
                        content_settings=self._content_settings(content_type),
                        metadata=custom_meta or None,
                    )
                    sha = hashlib.sha256(data).hexdigest()
                    size = len(data)
                else:
                    sha, size = await self._stream_upload(
                        blob, data, content_type, custom_meta
                    )
        except Exception as exc:
            raise UploadError(f"Azure upload failed for {blob_name}: {exc}") from exc

        meta = FileMetadata(
            content_type=content_type,
            size=size,
            checksum=sha,
            created_at=metadata.created_at if metadata else datetime.now(timezone.utc),
            custom_metadata=custom_meta,
        )
        return StoredFileReference(
            path=validate_path(path), metadata=meta, storage_backend="azure"
        )

    async def download(self, path: str) -> AsyncIterator[bytes]:
        blob_name = self._blob_name(path)
        container = self._get_container_client()
        try:
            async with container:
                blob = container.get_blob_client(blob_name)
                stream = await blob.download_blob()
                async for chunk in stream.chunks():
                    yield chunk
        except Exception as exc:
            if "BlobNotFound" in str(exc):
                raise BlobNotFoundError(validate_path(path)) from exc
            raise DownloadError(
                f"Azure download failed for {blob_name}: {exc}"
            ) from exc

    async def delete(self, path: str) -> None:
        blob_name = self._blob_name(path)
        container = self._get_container_client()
        async with container:
            blob = container.get_blob_client(blob_name)
            with contextlib.suppress(Exception):  # idempotent — ignore if absent
                await blob.delete_blob()

    async def get_presigned_url(
        self,
        path: str,
        method: str = "GET",
        expires_in: int = 3600,
    ) -> str:
        from azure.storage.blob import (
            BlobSasPermissions,
            generate_blob_sas,
        )

        blob_name = self._blob_name(path)
        method_upper = method.upper()

        if method_upper == "GET":
            permission = BlobSasPermissions(read=True)
        elif method_upper == "PUT":
            permission = BlobSasPermissions(write=True, create=True)
        else:
            raise PresignedUrlError(f"Unsupported method: {method}")

        if not self._account_name or not self._account_key:
            raise PresignedUrlError(
                "account_name and account_key are required for SAS generation"
            )

        try:
            sas = generate_blob_sas(
                account_name=self._account_name,
                container_name=self._container_name,
                blob_name=blob_name,
                account_key=self._account_key,
                permission=permission,
                expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            )
        except Exception as exc:
            raise PresignedUrlError(f"Failed to generate SAS token: {exc}") from exc

        return (
            f"https://{self._account_name}.blob.core.windows.net/"
            f"{self._container_name}/{blob_name}?{sas}"
        )

    async def exists(self, path: str) -> bool:
        blob_name = self._blob_name(path)
        container = self._get_container_client()
        async with container:
            blob = container.get_blob_client(blob_name)
            try:
                await blob.get_blob_properties()
            except Exception:
                return False
        return True

    async def get_metadata(self, path: str) -> FileMetadata:
        blob_name = self._blob_name(path)
        container = self._get_container_client()
        async with container:
            blob = container.get_blob_client(blob_name)
            try:
                props = await blob.get_blob_properties()
            except Exception as exc:
                raise BlobNotFoundError(validate_path(path)) from exc

        return FileMetadata(
            content_type=props.content_settings.content_type
            or "application/octet-stream",
            size=props.size,
            checksum=props.etag.strip('"') if props.etag else None,
            created_at=props.creation_time or datetime.now(timezone.utc),
            custom_metadata=dict(props.metadata) if props.metadata else {},
        )

    async def copy(self, source: str, destination: str) -> StoredFileReference:
        src_name = self._blob_name(source)
        dst_name = self._blob_name(destination)
        container = self._get_container_client()
        async with container:
            src_blob = container.get_blob_client(src_name)
            dst_blob = container.get_blob_client(dst_name)
            try:
                await dst_blob.start_copy_from_url(src_blob.url)
            except Exception as exc:
                raise UploadError(
                    f"Azure copy failed {src_name} → {dst_name}: {exc}"
                ) from exc

            try:
                props = await dst_blob.get_blob_properties()
            except Exception:
                props = None

        if props:
            meta = FileMetadata(
                content_type=props.content_settings.content_type
                or "application/octet-stream",
                size=props.size,
                created_at=props.creation_time or datetime.now(timezone.utc),
                custom_metadata=dict(props.metadata) if props.metadata else {},
            )
        else:
            meta = FileMetadata()

        return StoredFileReference(
            path=validate_path(destination),
            metadata=meta,
            storage_backend="azure",
        )

    async def list_prefix(self, prefix: str) -> AsyncIterator[StoredFileReference]:
        full_prefix = self._blob_name(prefix) if prefix else self._prefix
        container = self._get_container_client()
        async with container:
            async for blob in container.list_blobs(name_starts_with=full_prefix):
                name: str = blob.name
                rel = name.removeprefix(self._prefix) if self._prefix else name
                meta = FileMetadata(
                    size=blob.size,
                    content_type=blob.content_settings.content_type
                    or "application/octet-stream",
                    created_at=blob.creation_time or datetime.now(timezone.utc),
                )
                yield StoredFileReference(
                    path=rel, metadata=meta, storage_backend="azure"
                )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _content_settings(content_type: str) -> Any:
        from azure.storage.blob import ContentSettings

        return ContentSettings(content_type=content_type)

    @staticmethod
    async def _stream_upload(
        blob: Any,
        data: AsyncIterator[bytes],
        content_type: str,
        custom_meta: dict[str, str],
    ) -> tuple[str, int]:
        """Collect streaming data, hash, and upload."""
        sha = hashlib.sha256()
        chunks: list[bytes] = []
        total = 0
        async for chunk in data:
            chunks.append(chunk)
            sha.update(chunk)
            total += len(chunk)

        from azure.storage.blob import ContentSettings

        await blob.upload_blob(
            b"".join(chunks),
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
            metadata=custom_meta or None,
        )
        return sha.hexdigest(), total
