"""In-memory checkpoint store for testing."""

from __future__ import annotations

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry

from .ports import ICheckpointStore


class InMemoryCheckpointStore(ICheckpointStore):
    """In-memory checkpoint store for testing."""

    def __init__(self) -> None:
        self._positions: dict[str, int] = {}

    async def get_position(self, projection_name: str) -> int | None:
        return self._positions.get(projection_name)

    async def save_position(self, projection_name: str, position: int) -> None:
        registry = get_hook_registry()
        await registry.execute_all(
            f"checkpoint.save.{projection_name}",
            {
                "projection.name": projection_name,
                "projection.position": position,
                "correlation_id": get_correlation_id(),
            },
            lambda: self._save_position_internal(projection_name, position),
        )

    async def _save_position_internal(
        self, projection_name: str, position: int
    ) -> None:
        self._positions[projection_name] = position

    def clear(self) -> None:
        """Reset all positions (for tests)."""
        self._positions.clear()
