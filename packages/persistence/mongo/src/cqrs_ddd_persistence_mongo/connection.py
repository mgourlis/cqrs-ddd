"""MongoConnectionManager — Motor client lifecycle, pooling, health check."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .exceptions import MongoConnectionError

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient


class MongoConnectionManager:
    """Wrap Motor client with lifecycle and health-check helpers."""

    def __init__(
        self,
        url: str = "mongodb://localhost:27017",
        *,
        server_selection_timeout_ms: int = 5000,
        connect_timeout_ms: int = 10000,
        **kwargs: Any,
    ) -> None:
        self._url = url
        self._server_selection_timeout_ms = server_selection_timeout_ms
        self._connect_timeout_ms = connect_timeout_ms
        self._kwargs = kwargs
        self._client: AsyncIOMotorClient[Any] | None = None

    async def connect(self) -> AsyncIOMotorClient[Any]:
        """Create and cache the Motor client. Idempotent."""
        if self._client is not None:
            return self._client
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as e:
            raise MongoConnectionError(
                "motor is required; install with motor>=3.3.0"
            ) from e
        try:
            self._client = AsyncIOMotorClient(
                self._url,
                serverSelectionTimeoutMS=self._server_selection_timeout_ms,
                connectTimeoutMS=self._connect_timeout_ms,
                **self._kwargs,
            )
            return self._client
        except Exception as e:
            raise MongoConnectionError(str(e)) from e

    @property
    def client(self) -> AsyncIOMotorClient[Any]:
        """Return the Motor client; raises if not connected."""
        if self._client is None:
            raise MongoConnectionError("Not connected; call connect() first")
        return self._client

    def close(self) -> None:
        """Close the client (synchronous; Motor client.close() is sync)."""
        if self._client is not None:
            self._client.close()
            self._client = None

    async def health_check(self) -> bool:
        """Ping the server; return True if reachable."""
        if self._client is None:
            return False
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:  # noqa: BLE001
            return False
