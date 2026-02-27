"""In-memory session store for development and testing.

WARNING: This implementation is NOT suitable for production use.
It stores data in memory and will NOT work with multiple workers.

Use Redis-backed session store in production.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .ports import ISessionStore


class InMemorySessionStore(ISessionStore):
    """In-memory session store for development and testing only.

    ⚠️ WARNING: This implementation stores data in a local dictionary.
    It will NOT work in multi-worker environments (Gunicorn/Uvicorn with workers>1).

    Use a Redis-backed ISessionStore implementation for production.

    Example:
        ```python
        # For development/testing
        session_store = InMemorySessionStore()

        # Store OAuth state
        await session_store.store("oauth_state_xyz", {
            "state": "xyz",
            "pkce_verifier": "abc123",
            "redirect_uri": "/callback",
        }, ttl=300)

        # Retrieve it later
        data = await session_store.get("oauth_state_xyz")
        ```
    """

    def __init__(self) -> None:
        """Initialize the in-memory session store."""
        self._store: dict[str, tuple[dict[str, Any], datetime | None]] = {}

    async def store(
        self, key: str, data: dict[str, Any], ttl: int | None = None
    ) -> None:
        """Store session data.

        Args:
            key: Session key.
            data: Session data dictionary.
            ttl: Time-to-live in seconds (optional).
        """
        expires_at: datetime | None = None
        if ttl is not None and ttl > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        self._store[key] = (data, expires_at)

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve session data.

        Args:
            key: Session key.

        Returns:
            Session data or None if not found/expired.
        """
        entry = self._store.get(key)
        if entry is None:
            return None

        data, expires_at = entry

        # Check expiration
        if expires_at is not None and datetime.now(timezone.utc) > expires_at:
            del self._store[key]
            return None

        return data

    async def delete(self, key: str) -> None:
        """Delete session data.

        Args:
            key: Session key.
        """
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        """Check if session key exists.

        Args:
            key: Session key.

        Returns:
            True if key exists and not expired.
        """
        data = await self.get(key)
        return data is not None

    def clear_all(self) -> None:
        """Clear all session data.

        Useful for testing cleanup.
        """
        self._store.clear()


__all__: list[str] = ["InMemorySessionStore"]
