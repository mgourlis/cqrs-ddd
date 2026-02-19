"""SQS client management and queue URL resolution."""

from __future__ import annotations

from typing import Any

from aiobotocore.session import AioSession

from ..exceptions import MessagingConnectionError


class SQSConnectionManager:
    """Manages aiobotocore SQS client and optional queue URL resolution."""

    def __init__(
        self,
        region_name: str = "us-east-1",
        *,
        session: AioSession | None = None,
        **client_kwargs: Any,
    ) -> None:
        """Configure region and optional session/client kwargs."""
        self._region = region_name
        self._session = session or AioSession()
        self._client_kwargs = client_kwargs
        self._client: Any = None
        self._client_cm: Any = None

    async def get_client(self) -> Any:
        """Return shared SQS client; create if needed."""
        if self._client is None:
            self._client_cm = self._session.create_client(
                "sqs",
                region_name=self._region,
                **self._client_kwargs,
            )
            self._client = await self._client_cm.__aenter__()
        return self._client

    async def get_queue_url(self, queue_name: str) -> str:
        """Resolve queue name to queue URL."""
        client = await self.get_client()
        try:
            out = await client.get_queue_url(QueueName=queue_name)
            return str(out["QueueUrl"])
        except Exception as e:
            err = getattr(e, "response", {}) or {}
            if (
                err.get("Error", {}).get("Code")
                == "AWS.SimpleQueueService.NonExistentQueue"
            ):
                out = await client.create_queue(QueueName=queue_name)
                return str(out["QueueUrl"])
            raise MessagingConnectionError(str(e)) from e

    async def close(self) -> None:
        """Close the client if open."""
        if self._client_cm is not None:
            await self._client_cm.__aexit__(None, None, None)
            self._client_cm = None
            self._client = None

    async def health_check(self) -> bool:
        """Return True if we can list queues (lightweight check)."""
        try:
            client = await self.get_client()
            await client.list_queues(MaxResults=1)
            return True
        except Exception:  # noqa: BLE001
            return False
