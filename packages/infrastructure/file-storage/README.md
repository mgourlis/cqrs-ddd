# cqrs-ddd-file-storage

Blob management for the **CQRS/DDD Toolkit** — `IBlobStorage` protocol and cloud-provider adapters for file upload, download, and time-limited direct access URLs (Presigned URLs, SAS tokens, Signed URLs).

## Installation

```bash
# Core (protocol + value objects only)
pip install cqrs-ddd-file-storage

# With a specific backend
pip install "cqrs-ddd-file-storage[s3]"      # AWS S3 via aioboto3
pip install "cqrs-ddd-file-storage[azure]"    # Azure Blob Storage
pip install "cqrs-ddd-file-storage[gcs]"      # Google Cloud Storage
pip install "cqrs-ddd-file-storage[local]"    # Local filesystem (dev only)
pip install "cqrs-ddd-file-storage[minio]"    # MinIO (S3-compatible)
```

## Architecture

```
Domain / Application layers
       │
       ▼
  IBlobStorage (protocol)          IVirusScanner (protocol)
       │                                  │
       ├── S3BlobStorage ◄────── aioboto3 │
       ├── AzureBlobStorage ◄── azure SDK  │
       ├── GCSBlobStorage ◄──── gcloud SDK │
       └── LocalBlobStorage ◄── aiofiles   └── (ClamAV adapter, etc.)
```

Domain and application services depend **only** on `IBlobStorage` — never on provider SDKs directly. Concrete adapters are injected at the composition root.

## Quick Start

### Local Development

```python
from cqrs_ddd_file_storage import BlobPath, IBlobStorage
from cqrs_ddd_file_storage.local import LocalBlobStorage

storage: IBlobStorage = LocalBlobStorage(root="/tmp/blobs")

# Build a tenant-scoped path
path = BlobPath.build(
    tenant_id="tenant-1",
    entity_type="invoice",
    entity_id="inv-42",
    filename="scan.pdf",
)
# → "tenant-1/invoice/inv-42/scan.pdf"

# Upload
ref = await storage.upload(path, b"PDF content bytes...")
print(ref.metadata.size)      # 20
print(ref.metadata.checksum)  # SHA-256 hex digest

# Download (streaming)
async for chunk in await storage.download(path):
    process(chunk)

# Presigned URL (simulated for local)
url = await storage.get_presigned_url(path, method="GET", expires_in=600)
```

### AWS S3

```python
import aioboto3
from cqrs_ddd_file_storage.s3 import S3BlobStorage

session = aioboto3.Session()

storage = S3BlobStorage(
    bucket="my-bucket",
    client_factory=lambda: session.client("s3", region_name="eu-west-1"),
    prefix="uploads/",
)

# Direct-to-cloud upload (large files)
put_url = await storage.get_presigned_url("tenant/doc/1/large.bin", method="PUT")
# → Client uploads directly to S3 via this URL

# Pass-through upload (small files)
ref = await storage.upload("tenant/doc/1/small.txt", b"hello")
```

### Azure Blob Storage

```python
from cqrs_ddd_file_storage.azure import AzureBlobStorage

storage = AzureBlobStorage(
    connection_string="DefaultEndpointsProtocol=https;...",
    container_name="uploads",
    account_name="myaccount",
    account_key="mykey",
)

# SAS token URL
url = await storage.get_presigned_url("tenant/img/1/photo.jpg", method="GET")
# → https://myaccount.blob.core.windows.net/uploads/tenant/img/1/photo.jpg?sv=...&sig=...
```

### Google Cloud Storage

```python
from gcloud.aio.storage import Storage
from cqrs_ddd_file_storage.gcs import GCSBlobStorage

async def make_storage():
    return Storage()

storage = GCSBlobStorage(
    bucket="my-bucket",
    session_factory=make_storage,
    service_account_email="sa@project.iam.gserviceaccount.com",
)

# V4 Signed URL
url = await storage.get_presigned_url("tenant/report/1/data.csv")
```

## Key Types

### `IBlobStorage` (Protocol)

| Method | Signature | Description |
|--------|-----------|-------------|
| `upload` | `(path, data, metadata?) → StoredFileReference` | Upload bytes or async stream |
| `download` | `(path) → AsyncIterator[bytes]` | Stream blob contents |
| `delete` | `(path) → None` | Delete (idempotent) |
| `get_presigned_url` | `(path, method?, expires_in?) → str` | Time-limited direct access URL |
| `exists` | `(path) → bool` | Check blob existence |
| `get_metadata` | `(path) → FileMetadata` | Retrieve blob metadata |
| `copy` | `(source, destination) → StoredFileReference` | Server-side copy |
| `list_prefix` | `(prefix) → AsyncIterator[StoredFileReference]` | List blobs by prefix |

### `FileMetadata` (Frozen Dataclass)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `content_type` | `str` | `"application/octet-stream"` | MIME type |
| `size` | `int \| None` | `None` | Size in bytes |
| `checksum` | `str \| None` | `None` | SHA-256 hex digest |
| `created_at` | `datetime` | `utcnow()` | Creation timestamp |
| `custom_metadata` | `dict[str, str]` | `{}` | Provider-agnostic metadata |

### `StoredFileReference` (Frozen Dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `path` | `str` | Canonical storage path |
| `metadata` | `FileMetadata` | Blob metadata |
| `storage_backend` | `str` | Backend identifier (`"s3"`, `"azure"`, `"local"`, etc.) |

### `BlobPath`

Structured path builder enforcing tenant isolation:

```python
BlobPath.build(tenant_id="t1", entity_type="invoice", entity_id="inv-1", filename="scan.pdf")
# → "t1/invoice/inv-1/scan.pdf"
```

**Security:** Rejects path traversal (`../`), absolute paths (`/etc/passwd`), and backslash separators.

### `IVirusScanner` (Protocol)

Optional hook for pass-through uploads:

```python
result = await scanner.scan(data)
if result.is_clean:
    ref = await storage.upload(path, data, metadata)
```

Returns `ScanResult` with `ScanVerdict.CLEAN | INFECTED | ERROR`.

## Upload Flows

### Flow A: Direct-to-Cloud (Large Files)

```
Client  ──GET presigned URL──▶  API  ──get_presigned_url()──▶  S3/Azure/GCS
Client  ────PUT file──────────────────────────────────────────▶  S3/Azure/GCS
                                        webhook / event bridge ──▶  API
```

### Flow B: Pass-Through (Small Files / Strict Validation)

```
Client  ──POST file──▶  API  ──scan()──▶  IVirusScanner
                              ──upload()──▶  IBlobStorage
                        ◀── StoredFileReference
```

## Time-Limited URL Support

| Provider | Name | Method |
|----------|------|--------|
| **AWS S3** | Presigned URL | `generate_presigned_url()` |
| **Azure** | SAS Token | `generate_blob_sas()` |
| **GCP** | Signed URL (V4) | `generate_signed_url(version="v4")` |
| **Local** | Dev endpoint | Simulated URL with query params |

## Exceptions

All exceptions inherit from `FileStorageError` → `InfrastructureError` → `CQRSDDDError`.

| Exception | When |
|-----------|------|
| `BlobNotFoundError` | Blob does not exist at the given path |
| `QuotaExceededError` | Storage quota or size limit exceeded |
| `PathTraversalError` | Path contains `../`, absolute paths, or backslashes |
| `UploadError` | Upload operation fails |
| `DownloadError` | Download / streaming read fails |
| `PresignedUrlError` | Presigned / signed URL generation fails |

## S3 Multipart Upload

The S3 adapter transparently uses multipart upload when receiving an `AsyncIterator[bytes]`. Chunks are buffered to 8 MiB parts and streamed using `create_multipart_upload` / `upload_part` / `complete_multipart_upload`. On failure, the multipart upload is automatically aborted.

## Testing

```bash
# Run unit tests (local adapter, protocols, value objects)
pytest packages/infrastructure/file-storage/file_storage_tests/ -v

# With coverage
pytest packages/infrastructure/file-storage/file_storage_tests/ --cov=packages/infrastructure/file-storage/src/cqrs_ddd_file_storage
```

For S3 integration tests, use LocalStack or MinIO via `testcontainers`.

## Package Structure

```
src/cqrs_ddd_file_storage/
├── __init__.py        # Public API exports
├── ports.py           # IBlobStorage protocol
├── metadata.py        # FileMetadata, StoredFileReference (frozen dataclasses)
├── path.py            # BlobPath builder + validate_path()
├── virus_scan.py      # IVirusScanner protocol, ScanResult, ScanVerdict
├── exceptions.py      # FileStorageError hierarchy
├── local.py           # LocalBlobStorage (aiofiles, dev only)
├── s3.py              # S3BlobStorage (aioboto3, presigned URLs)
├── azure.py           # AzureBlobStorage (azure-storage-blob, SAS)
└── gcs.py             # GCSBlobStorage (gcloud-aio-storage, signed URLs)
```
