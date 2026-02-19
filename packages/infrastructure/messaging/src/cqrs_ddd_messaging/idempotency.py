"""IdempotencyFilter —
deduplicate by message_id using ICacheService or in-memory set."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.cache import ICacheService


class IdempotencyFilter:
    """Deduplicate messages by message_id to prevent double-execution on redelivery.

    Uses ICacheService when provided (e.g. Redis); otherwise uses an in-memory set
    for testing. When using cache, keys expire after ttl_seconds.
    """

    def __init__(
        self,
        cache: ICacheService | None = None,
        *,
        key_prefix: str = "idempotency:",
        ttl_seconds: int = 86400,
    ) -> None:
        """Configure the filter.

        Args:
            cache: Optional cache for distributed idempotency.
            If None, uses in-memory set.
            key_prefix: Prefix for cache keys.
            ttl_seconds: TTL for cache entries (ignored for in-memory).
        """
        self._cache = cache
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._seen: set[str] = set()

    def _key(self, message_id: str) -> str:
        return f"{self._key_prefix}{message_id}"

    async def is_duplicate(self, message_id: str) -> bool:
        """Return True if this message_id has already been processed."""
        if self._cache is not None:
            value = await self._cache.get(self._key(message_id))
            return value is not None
        return message_id in self._seen

    async def mark_processed(self, message_id: str) -> None:
        """Record that this message_id has been processed."""
        if self._cache is not None:
            await self._cache.set(
                self._key(message_id),
                "1",
                ttl=self._ttl_seconds,
            )
        else:
            self._seen.add(message_id)

    def clear_memory(self) -> None:
        """Clear in-memory seen set (for testing). No-op when using cache."""
        self._seen.clear()
