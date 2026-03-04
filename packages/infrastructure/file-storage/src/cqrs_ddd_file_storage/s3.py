"""AWS S3 adapter for :class:`IBlobStorage`.

Requires the ``[s3]`` extra (``aioboto3>=12.0``).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .exceptions import (
    BlobNotFoundError,
    DownloadError,
    PresignedUrlError,
    UploadError,
)
from .metadata import FileMetadata, StoredFileReference
from .path import validate_path
from .ports import IBlobStorage

if TYPE_CHECKING:
    from types_aiobotocore_s3.client import S3Client

logger = logging.getLogger(__name__)

_MULTIPART_THRESHOLD = 5 * 1024 * 1024  # 5 MiB
_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB


class S3BlobStorage(IBlobStorage):
    """S3-backed blob storage with presigned URL support.

    Parameters:
        bucket: S3 bucket name.
        client_factory: Async callable returning an ``S3Client`` session.
            Typically ``aioboto3.Session().client("s3", ...)``.
        prefix: Optional key prefix applied to all paths (e.g. ``"uploads/"``).
    """

    def __init__(
        self,
        bucket: str,
        client_factory: Any,
        *,
        prefix: str = "",
    ) -> None:
        self._bucket = bucket
        self._client_factory = client_factory
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""

    def _key(self, path: str) -> str:
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
        key = self._key(path)
        extra: dict[str, Any] = {}
        if metadata and metadata.content_type:
            extra["ContentType"] = metadata.content_type
        if metadata and metadata.custom_metadata:
            extra["Metadata"] = metadata.custom_metadata

        try:
            async with self._client_factory() as client:
                if isinstance(data, bytes):
                    await client.put_object(
                        Bucket=self._bucket,
                        Key=key,
                        Body=data,
                        **extra,
                    )
                    sha = hashlib.sha256(data).hexdigest()
                    size = len(data)
                else:
                    # Streaming upload via multipart
                    sha, size = await self._multipart_upload(client, key, data, extra)

        except Exception as exc:
            raise UploadError(f"S3 upload failed for {key}: {exc}") from exc

        meta = FileMetadata(
            content_type=metadata.content_type
            if metadata
            else "application/octet-stream",
            size=size,
            checksum=sha,
            created_at=metadata.created_at if metadata else datetime.now(timezone.utc),
            custom_metadata=dict(metadata.custom_metadata) if metadata else {},
        )
        return StoredFileReference(
            path=validate_path(path), metadata=meta, storage_backend="s3"
        )

    async def download(self, path: str) -> AsyncIterator[bytes]:
        key = self._key(path)
        try:
            async with self._client_factory() as client:
                resp = await client.get_object(Bucket=self._bucket, Key=key)
                async for chunk in resp["Body"]:
                    yield chunk
        except client.exceptions.NoSuchKey:
            raise BlobNotFoundError(validate_path(path)) from None
        except Exception as exc:
            raise DownloadError(f"S3 download failed for {key}: {exc}") from exc

    async def delete(self, path: str) -> None:
        key = self._key(path)
        async with self._client_factory() as client:
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def get_presigned_url(
        self,
        path: str,
        method: str = "GET",
        expires_in: int = 3600,
    ) -> str:
        key = self._key(path)
        method_upper = method.upper()
        try:
            async with self._client_factory() as client:
                if method_upper == "GET":
                    url: str = await client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": self._bucket, "Key": key},
                        ExpiresIn=expires_in,
                    )
                elif method_upper == "PUT":
                    url = await client.generate_presigned_url(
                        "put_object",
                        Params={"Bucket": self._bucket, "Key": key},
                        ExpiresIn=expires_in,
                    )
                else:
                    raise PresignedUrlError(f"Unsupported method: {method}")
        except PresignedUrlError:
            raise
        except Exception as exc:
            raise PresignedUrlError(f"Failed to generate presigned URL: {exc}") from exc
        return url

    async def exists(self, path: str) -> bool:
        key = self._key(path)
        async with self._client_factory() as client:
            try:
                await client.head_object(Bucket=self._bucket, Key=key)
            except Exception:
                return False
        return True

    async def get_metadata(self, path: str) -> FileMetadata:
        key = self._key(path)
        async with self._client_factory() as client:
            try:
                head = await client.head_object(Bucket=self._bucket, Key=key)
            except Exception as exc:
                raise BlobNotFoundError(validate_path(path)) from exc
        return FileMetadata(
            content_type=head.get("ContentType", "application/octet-stream"),
            size=head.get("ContentLength"),
            checksum=head.get("ETag", "").strip('"'),
            created_at=head.get("LastModified", datetime.now(timezone.utc)),
            custom_metadata=head.get("Metadata", {}),
        )

    async def copy(self, source: str, destination: str) -> StoredFileReference:
        src_key = self._key(source)
        dst_key = self._key(destination)
        async with self._client_factory() as client:
            try:
                await client.copy_object(
                    Bucket=self._bucket,
                    Key=dst_key,
                    CopySource={"Bucket": self._bucket, "Key": src_key},
                )
            except Exception as exc:
                raise UploadError(
                    f"S3 copy failed {src_key} → {dst_key}: {exc}"
                ) from exc

            try:
                head = await client.head_object(Bucket=self._bucket, Key=dst_key)
            except Exception:
                head = {}

        meta = FileMetadata(
            content_type=head.get("ContentType", "application/octet-stream"),
            size=head.get("ContentLength"),
            created_at=head.get("LastModified", datetime.now(timezone.utc)),
            custom_metadata=head.get("Metadata", {}),
        )
        return StoredFileReference(
            path=validate_path(destination),
            metadata=meta,
            storage_backend="s3",
        )

    async def list_prefix(self, prefix: str) -> AsyncIterator[StoredFileReference]:
        full_prefix = self._key(prefix) if prefix else self._prefix
        async with self._client_factory() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self._bucket, Prefix=full_prefix
            ):
                for obj in page.get("Contents", []):
                    key: str = obj["Key"]
                    rel = key.removeprefix(self._prefix) if self._prefix else key
                    meta = FileMetadata(
                        size=obj.get("Size"),
                        created_at=obj.get("LastModified", datetime.now(timezone.utc)),
                    )
                    yield StoredFileReference(
                        path=rel, metadata=meta, storage_backend="s3"
                    )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _multipart_upload(
        self,
        client: S3Client,
        key: str,
        data: AsyncIterator[bytes],
        extra: dict[str, Any],
    ) -> tuple[str, int]:
        """Stream an async iterator via S3 multipart upload.

        Returns ``(sha256_hex, total_size)``.
        """
        sha = hashlib.sha256()
        mpu = await client.create_multipart_upload(
            Bucket=self._bucket, Key=key, **extra
        )
        upload_id = mpu["UploadId"]
        parts: list[dict[str, Any]] = []
        part_number = 1
        total_size = 0
        buffer = bytearray()

        try:
            async for chunk in data:
                buffer.extend(chunk)
                sha.update(chunk)
                total_size += len(chunk)

                while len(buffer) >= _CHUNK_SIZE:
                    part_data = bytes(buffer[:_CHUNK_SIZE])
                    del buffer[:_CHUNK_SIZE]
                    resp = await client.upload_part(
                        Bucket=self._bucket,
                        Key=key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=part_data,
                    )
                    parts.append({"ETag": resp["ETag"], "PartNumber": part_number})
                    part_number += 1

            # Flush remainder
            if buffer:
                resp = await client.upload_part(
                    Bucket=self._bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=bytes(buffer),
                )
                parts.append({"ETag": resp["ETag"], "PartNumber": part_number})

            await client.complete_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception:
            await client.abort_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
            )
            raise

        return sha.hexdigest(), total_size
