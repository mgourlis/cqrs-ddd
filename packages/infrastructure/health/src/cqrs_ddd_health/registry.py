"""Health check registry — aggregates component health."""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class HealthRegistry:
    """Singleton registry for health checks and worker heartbeats."""

    _instance: HealthRegistry | None = None

    def __init__(self, heartbeat_timeout_seconds: int = 60) -> None:
        self._checks: dict[str, Callable[[], Any]] = {}
        self._heartbeats: dict[str, datetime.datetime] = {}
        self._heartbeat_timeout = heartbeat_timeout_seconds

    @classmethod
    def get_instance(cls) -> HealthRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, name: str, check: Callable[[], Any]) -> None:
        """Register a health check."""
        self._checks[name] = check

    def heartbeat(self, worker_name: str) -> None:
        """Record worker heartbeat time."""
        self._heartbeats[worker_name] = datetime.datetime.now(datetime.timezone.utc)

    def _check_heartbeats(self) -> dict[str, str]:
        now = datetime.datetime.now(datetime.timezone.utc)
        results: dict[str, str] = {}
        for worker_name, last_heartbeat in self._heartbeats.items():
            age = (now - last_heartbeat).total_seconds()
            results[worker_name] = "up" if age < self._heartbeat_timeout else "down"
        return results

    async def check_all(self) -> dict[str, str]:
        """Run all checks and return status map."""
        result: dict[str, str] = {}
        for name, check in self._checks.items():
            try:
                value = check()
                if asyncio.iscoroutine(value):
                    value = await value
                result[name] = "up" if value else "down"
            except Exception:  # noqa: BLE001
                result[name] = "down"

        result.update(self._check_heartbeats())
        return result

    async def status(self) -> dict[str, Any]:
        """Return full health status report."""
        components = await self.check_all()
        healthy = all(v == "up" for v in components.values())
        return {
            "status": "healthy" if healthy else "unhealthy",
            "components": components,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "heartbeats": {
                name: ts.isoformat() for name, ts in self._heartbeats.items()
            },
        }
