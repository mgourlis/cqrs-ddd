"""Google Cloud Storage adapter for :class:`IBlobStorage`.

Requires the ``[gcs]`` extra (``gcloud-aio-storage``).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
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

_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB


class GCSBlobStorage(IBlobStorage):
    """Google Cloud Storage adapter with Signed URL support.

    Parameters:
        bucket: GCS bucket name.
        session_factory: Async callable returning a ``gcloud.aio.storage.Storage``
            instance (or any compatible async GCS client).
        prefix: Optional key prefix applied to all object names.
        service_account_email: Email of the service account used for signing.
        service_account_key: PEM private key for V4 signature generation.
            If not provided, IAM-based signing is used.
    """

    def __init__(
        self,
        bucket: str,
        session_factory: Any,
        *,
        prefix: str = "",
        service_account_email: str = "",
        service_account_key: str = "",
    ) -> None:
        self._bucket = bucket
        self._session_factory = session_factory
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._sa_email = service_account_email
        self._sa_key = service_account_key

    def _object_name(self, path: str) -> str:
        return f"{self._prefix}{validate_path(path)}"

    # ------------------------------------------------------------------
    # IBlobStorage
    # ------------------------------------------------------------------

    async def upload(
        self,
        path: str,
        data: bytes | AsyncIterator[bytes],
        metadata: FileMetadata | None = None,
    ) -> StoredFileReference:
        obj_name = self._object_name(path)
        content_type = metadata.content_type if metadata else "application/octet-stream"
        custom_meta = (
            dict(metadata.custom_metadata)
            if metadata and metadata.custom_metadata
            else {}
        )

        try:
            storage = await self._session_factory()
            if isinstance(data, bytes):
                payload = data
                sha = hashlib.sha256(data).hexdigest()
                size = len(data)
            else:
                chunks: list[bytes] = []
                sha_h = hashlib.sha256()
                async for chunk in data:
                    chunks.append(chunk)
                    sha_h.update(chunk)
                payload = b"".join(chunks)
                sha = sha_h.hexdigest()
                size = len(payload)

            await storage.upload(
                self._bucket,
                obj_name,
                payload,
                metadata=custom_meta or None,
                headers={"Content-Type": content_type},
            )
            await storage.close()
        except Exception as exc:
            raise UploadError(f"GCS upload failed for {obj_name}: {exc}") from exc

        meta = FileMetadata(
            content_type=content_type,
            size=size,
            checksum=sha,
            created_at=metadata.created_at if metadata else datetime.now(timezone.utc),
            custom_metadata=custom_meta,
        )
        return StoredFileReference(
            path=validate_path(path), metadata=meta, storage_backend="gcs"
        )

    async def download(self, path: str) -> AsyncIterator[bytes]:
        obj_name = self._object_name(path)
        try:
            storage = await self._session_factory()
            blob_bytes: bytes = await storage.download(self._bucket, obj_name)
            await storage.close()
        except Exception as exc:
            if "404" in str(exc) or "Not Found" in str(exc):
                raise BlobNotFoundError(validate_path(path)) from exc
            raise DownloadError(f"GCS download failed for {obj_name}: {exc}") from exc

        # Yield in chunks for consistency with the streaming protocol
        offset = 0
        while offset < len(blob_bytes):
            yield blob_bytes[offset : offset + _CHUNK_SIZE]
            offset += _CHUNK_SIZE

    async def delete(self, path: str) -> None:
        obj_name = self._object_name(path)
        try:
            storage = await self._session_factory()
            await storage.delete(self._bucket, obj_name)
            await storage.close()
        except Exception:
            pass  # idempotent — ignore if already absent

    async def get_presigned_url(
        self,
        path: str,
        method: str = "GET",
        expires_in: int = 3600,
    ) -> str:
        from gcloud.aio.storage import Storage

        obj_name = self._object_name(path)
        method_upper = method.upper()
        if method_upper not in ("GET", "PUT"):
            raise PresignedUrlError(f"Unsupported method: {method}")

        try:
            storage: Storage = await self._session_factory()
            blob = storage.get_blob(self._bucket, obj_name)
            url: str = await blob.get_signed_url(
                expiration=expires_in,
                http_method=method_upper,
                version="v4",
                service_account_email=self._sa_email or None,
                access_token=None,
            )
            await storage.close()
        except PresignedUrlError:
            raise
        except Exception as exc:
            raise PresignedUrlError(
                f"Failed to generate GCS signed URL: {exc}"
            ) from exc
        return url

    async def exists(self, path: str) -> bool:
        obj_name = self._object_name(path)
        try:
            storage = await self._session_factory()
            metadata = await storage.download_metadata(self._bucket, obj_name)
            await storage.close()
            return metadata is not None
        except Exception:
            return False

    async def get_metadata(self, path: str) -> FileMetadata:
        obj_name = self._object_name(path)
        try:
            storage = await self._session_factory()
            gcs_meta = await storage.download_metadata(self._bucket, obj_name)
            await storage.close()
        except Exception as exc:
            raise BlobNotFoundError(validate_path(path)) from exc

        if gcs_meta is None:
            raise BlobNotFoundError(validate_path(path))

        return FileMetadata(
            content_type=gcs_meta.get("contentType", "application/octet-stream"),
            size=int(gcs_meta["size"]) if "size" in gcs_meta else None,
            checksum=gcs_meta.get("md5Hash"),
            created_at=datetime.fromisoformat(gcs_meta["timeCreated"])
            if "timeCreated" in gcs_meta
            else datetime.now(timezone.utc),
            custom_metadata=gcs_meta.get("metadata", {}),
        )

    async def copy(self, source: str, destination: str) -> StoredFileReference:
        src_name = self._object_name(source)
        dst_name = self._object_name(destination)
        try:
            storage = await self._session_factory()
            await storage.copy(
                self._bucket,
                src_name,
                self._bucket,
                new_name=dst_name,
            )
            gcs_meta = await storage.download_metadata(self._bucket, dst_name)
            await storage.close()
        except Exception as exc:
            raise UploadError(
                f"GCS copy failed {src_name} → {dst_name}: {exc}"
            ) from exc

        meta = FileMetadata(
            content_type=gcs_meta.get("contentType", "application/octet-stream")
            if gcs_meta
            else "application/octet-stream",
            size=int(gcs_meta["size"]) if gcs_meta and "size" in gcs_meta else None,
            created_at=datetime.now(timezone.utc),
            custom_metadata=gcs_meta.get("metadata", {}) if gcs_meta else {},
        )
        return StoredFileReference(
            path=validate_path(destination),
            metadata=meta,
            storage_backend="gcs",
        )

    async def list_prefix(self, prefix: str) -> AsyncIterator[StoredFileReference]:
        full_prefix = self._object_name(prefix) if prefix else self._prefix
        try:
            storage = await self._session_factory()
            blobs = await storage.list_objects(
                self._bucket, params={"prefix": full_prefix}
            )
            await storage.close()
        except Exception:
            return

        for item in blobs.get("items", []):
            name: str = item["name"]
            rel = name.removeprefix(self._prefix) if self._prefix else name
            meta = FileMetadata(
                size=int(item["size"]) if "size" in item else None,
                content_type=item.get("contentType", "application/octet-stream"),
                created_at=datetime.fromisoformat(item["timeCreated"])
                if "timeCreated" in item
                else datetime.now(timezone.utc),
            )
            yield StoredFileReference(path=rel, metadata=meta, storage_backend="gcs")
