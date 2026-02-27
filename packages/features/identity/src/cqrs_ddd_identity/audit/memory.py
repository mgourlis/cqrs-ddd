"""In-memory audit store for testing and development.

This module provides a simple in-memory implementation of IAuthAuditStore
suitable for testing and development environments.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ..ports import IAuthAuditStore

if TYPE_CHECKING:
    from .events import AuthAuditEvent, AuthEventType


class InMemoryAuthAuditStore(IAuthAuditStore):
    """In-memory implementation of IAuthAuditStore.

    Stores audit events in memory with support for filtering by
    principal, event type, and time range.

    Note:
        Events are stored in memory and will be lost on restart.
        Not suitable for production use.

    Example:
        ```python
        store = InMemoryAuthAuditStore()

        # Record an event
        await store.record(login_success_event(
            principal_id="user-123",
            provider="keycloak",
        ))

        # Query events
        events = await store.get_events("user-123")
        ```
    """

    def __init__(self) -> None:
        """Initialize the in-memory audit store."""
        self._events: list[AuthAuditEvent] = []
        self._by_principal: dict[str, list[int]] = defaultdict(list)
        self._by_type: dict[str, list[int]] = defaultdict(list)

    async def record(self, event: AuthAuditEvent) -> None:
        """Record an audit event.

        Args:
            event: The audit event to record.
        """
        index = len(self._events)
        self._events.append(event)

        # Index by principal
        if event.principal_id:
            self._by_principal[event.principal_id].append(index)

        # Index by event type
        self._by_type[event.event_type.value].append(index)

    async def get_events(
        self,
        principal_id: str,
        *,
        event_types: list[AuthEventType] | None = None,
        limit: int = 100,
    ) -> list[AuthAuditEvent]:
        """Get audit events for a principal.

        Args:
            principal_id: User/service ID to query.
            event_types: Optional filter by event types.
            limit: Maximum number of events to return.

        Returns:
            List of audit events, most recent first.
        """
        indices = self._by_principal.get(principal_id, [])

        results: list[AuthAuditEvent] = []
        for idx in reversed(indices):  # Most recent first
            event = self._events[idx]

            # Filter by event type if specified
            if event_types and event.event_type not in event_types:
                continue

            results.append(event)

            if len(results) >= limit:
                break

        return results

    async def get_events_by_type(
        self,
        event_type: AuthEventType,
        *,
        limit: int = 100,
    ) -> list[AuthAuditEvent]:
        """Get audit events by type across all principals.

        Args:
            event_type: Event type to query.
            limit: Maximum number of events to return.

        Returns:
            List of audit events, most recent first.
        """
        indices = self._by_type.get(event_type.value, [])

        results: list[AuthAuditEvent] = []
        for idx in reversed(indices):  # Most recent first
            event = self._events[idx]
            results.append(event)

            if len(results) >= limit:
                break

        return results

    async def get_recent_failures(
        self,
        *,
        principal_id: str | None = None,
        minutes: int = 15,
        limit: int = 100,
    ) -> list[AuthAuditEvent]:
        """Get recent failed authentication events.

        Args:
            principal_id: Optional filter by principal.
            minutes: Time window in minutes.
            limit: Maximum number of events to return.

        Returns:
            List of failed authentication events.
        """
        from .events import AuthEventType

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        failure_types = {
            AuthEventType.LOGIN_FAILED,
            AuthEventType.MFA_FAILED,
            AuthEventType.PASSWORD_FAILED,
            AuthEventType.TOKEN_EXPIRED,
        }

        results: list[AuthAuditEvent] = []

        # Use principal index if filtering by principal
        if principal_id:
            indices = self._by_principal.get(principal_id, [])
        else:
            indices = list(range(len(self._events)))

        for idx in reversed(indices):
            event = self._events[idx]

            # Check time window
            if event.timestamp < cutoff:
                continue

            # Check if it's a failure event
            if event.event_type not in failure_types and not (
                not event.success and event.event_type.value.endswith(".failed")
            ):
                continue

            # Include failed events (success=False) or specific failure types
            if event.event_type in failure_types or not event.success:
                results.append(event)

            if len(results) >= limit:
                break

        return results

    def clear(self) -> None:
        """Clear all stored events.

        Useful for test cleanup.
        """
        self._events.clear()
        self._by_principal.clear()
        self._by_type.clear()

    def count(self) -> int:
        """Get total number of stored events.

        Returns:
            Total event count.
        """
        return len(self._events)

    def count_by_type(self, event_type: AuthEventType) -> int:
        """Get count of events by type.

        Args:
            event_type: Event type to count.

        Returns:
            Number of events of that type.
        """
        return len(self._by_type.get(event_type.value, []))

    def count_by_principal(self, principal_id: str) -> int:
        """Get count of events for a principal.

        Args:
            principal_id: Principal ID to count.

        Returns:
            Number of events for that principal.
        """
        return len(self._by_principal.get(principal_id, []))


__all__: list[str] = ["InMemoryAuthAuditStore"]
