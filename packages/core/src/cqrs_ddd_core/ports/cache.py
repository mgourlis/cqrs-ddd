"""ICacheService - Protocol for cache operations."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ICacheService(Protocol):
    """
    Abstract interface for caching services.
    Supports basic get/set/delete and batch operations.
    """

    async def get(self, key: str, cls: type[Any] | None = None) -> Any | None:
        """
        Retrieve a value by key. Returns None if missing.
        If cls is provided and is a Pydantic model, validation is performed.
        """
        ...

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Set a value with optional TTL (in seconds).
        Host implementation should handle serialization.
        """
        ...

    async def delete(self, key: str) -> None:
        """Delete a value by key."""
        ...

    async def get_batch(
        self, keys: list[str], cls: type[Any] | None = None
    ) -> list[Any | None]:
        """
        Retrieve multiple values.
        Returns list of values in same order as keys (None for missing).
        """
        ...

    async def set_batch(
        self, items: list[dict[str, Any]], ttl: int | None = None
    ) -> None:
        """
        Set multiple values.
        Items should be list of dicts: {"cache_key": str, "value": Any}
        """
        ...

    async def delete_batch(self, keys: list[str]) -> None:
        """Delete multiple keys."""
        ...

    async def clear_namespace(self, prefix: str) -> None:
        """Clear all keys starting with prefix."""
        ...
