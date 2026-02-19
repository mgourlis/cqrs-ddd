"""Kafka bootstrap and health check."""

from __future__ import annotations

from typing import Any

from aiokafka.admin import AIOKafkaAdminClient


class KafkaConnectionManager:
    """Holds Kafka bootstrap config and optional admin client for health checks.

    Does not hold a long-lived producer/consumer; those are created per
    publisher/consumer with the same bootstrap_servers.
    """

    def __init__(
        self,
        bootstrap_servers: str | list[str] = "localhost:9092",
        **config: Any,
    ) -> None:
        """Configure bootstrap servers and optional aiokafka client kwargs."""
        self._bootstrap_servers = bootstrap_servers
        self._config = config

    @property
    def bootstrap_servers(self) -> str | list[str]:
        return self._bootstrap_servers

    def producer_config(self) -> dict[str, Any]:
        """Config dict for AIOKafkaProducer."""
        return {"bootstrap_servers": self._bootstrap_servers, **self._config}

    def consumer_config(self) -> dict[str, Any]:
        """Config dict for AIOKafkaConsumer."""
        return {"bootstrap_servers": self._bootstrap_servers, **self._config}

    async def health_check(self) -> bool:
        """Return True if the cluster is reachable."""
        try:
            admin = AIOKafkaAdminClient(
                bootstrap_servers=self._bootstrap_servers,
                **{k: v for k, v in self._config.items() if k != "group_id"},
            )
            await admin.start()
            try:
                await admin.list_topics()
                return True
            finally:
                await admin.close()
        except Exception:  # noqa: BLE001
            return False
