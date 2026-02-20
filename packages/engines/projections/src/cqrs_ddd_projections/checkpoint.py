"""In-memory checkpoint store for testing."""

from __future__ import annotations

from .ports import ICheckpointStore


class InMemoryCheckpointStore(ICheckpointStore):
    """In-memory checkpoint store for testing."""

    def __init__(self) -> None:
        self._positions: dict[str, int] = {}

    async def get_position(self, projection_name: str) -> int | None:
        return self._positions.get(projection_name)

    async def save_position(self, projection_name: str, position: int) -> None:
        self._positions[projection_name] = position

    def clear(self) -> None:
        """Reset all positions (for tests)."""
        self._positions.clear()
