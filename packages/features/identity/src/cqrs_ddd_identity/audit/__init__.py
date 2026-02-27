"""Audit module for authentication events.

This module provides audit event types, storage protocols, and
in-memory implementations for tracking authentication activities.
"""

from __future__ import annotations

from .events import (
    AuthAuditEvent,
    AuthEventType,
    api_key_used_event,
    login_failed_event,
    login_success_event,
    logout_event,
    mfa_verified_event,
    session_created_event,
    session_destroyed_event,
    token_refreshed_event,
)
from .memory import InMemoryAuthAuditStore

__all__: list[str] = [
    # Event types and classes
    "AuthEventType",
    "AuthAuditEvent",
    # Event factory functions
    "login_success_event",
    "login_failed_event",
    "logout_event",
    "token_refreshed_event",
    "mfa_verified_event",
    "api_key_used_event",
    "session_created_event",
    "session_destroyed_event",
    # Store implementations
    "InMemoryAuthAuditStore",
]
