"""Audit events for authentication operations.

This module provides standardized audit events for tracking authentication
activities across all identity providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AuthEventType(Enum):
    """Types of authentication audit events.

    Event naming follows the pattern: `auth.<resource>.<action>`
    """

    # Login events
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILED = "auth.login.failed"
    LOGOUT = "auth.logout"

    # Token events
    TOKEN_REFRESHED = "auth.token.refreshed"  # noqa: S105
    TOKEN_REVOKED = "auth.token.revoked"  # noqa: S105
    TOKEN_EXPIRED = "auth.token.expired"  # noqa: S105

    # MFA events
    MFA_ENABLED = "auth.mfa.enabled"
    MFA_DISABLED = "auth.mfa.disabled"
    MFA_VERIFIED = "auth.mfa.verified"
    MFA_FAILED = "auth.mfa.failed"
    MFA_RESET = "auth.mfa.reset"

    # API Key events
    API_KEY_CREATED = "auth.apikey.created"
    API_KEY_REVOKED = "auth.apikey.revoked"
    API_KEY_USED = "auth.apikey.used"
    API_KEY_EXPIRED = "auth.apikey.expired"

    # Session events
    SESSION_CREATED = "auth.session.created"
    SESSION_DESTROYED = "auth.session.destroyed"
    SESSION_EXPIRED = "auth.session.expired"

    # Password events
    PASSWORD_CHANGED = "auth.password.changed"  # noqa: S105
    PASSWORD_RESET_REQUESTED = "auth.password.reset_requested"  # noqa: S105
    PASSWORD_RESET_COMPLETED = "auth.password.reset_completed"  # noqa: S105
    PASSWORD_FAILED = "auth.password.failed"  # noqa: S105

    # User management events
    USER_CREATED = "auth.user.created"
    USER_UPDATED = "auth.user.updated"
    USER_DELETED = "auth.user.deleted"
    USER_LOCKED = "auth.user.locked"
    USER_UNLOCKED = "auth.user.unlocked"


@dataclass(frozen=True)
class AuthAuditEvent:
    """Authentication audit event.

    Captures all relevant information about an authentication-related
    operation for auditing, compliance, and security monitoring.

    Attributes:
        event_type: The type of authentication event.
        principal_id: The user/service ID associated with the event.
        provider: The identity provider that generated the event.
        timestamp: When the event occurred (UTC).
        ip_address: Client IP address (if available).
        user_agent: Client user agent string (if available).
        request_id: Correlation ID for request tracing.
        session_id: Session identifier (if applicable).
        success: Whether the operation was successful.
        error_code: Error code if operation failed.
        error_message: Human-readable error message if failed.
        metadata: Additional event-specific data.
    """

    event_type: AuthEventType
    principal_id: str | None = None
    provider: str = "unknown"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    success: bool = True
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate event data."""
        if not self.success and not self.error_code:
            object.__setattr__(self, "error_code", "UNKNOWN_ERROR")

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "event_type": self.event_type.value,
            "principal_id": self.principal_id,
            "provider": self.provider,
            "timestamp": self.timestamp.isoformat(),
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "success": self.success,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthAuditEvent:
        """Create event from dictionary.

        Args:
            data: Dictionary representation.

        Returns:
            AuthAuditEvent instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        event_type_str = data.get("event_type")
        if event_type_str is None:
            raise ValueError("Missing required 'event_type'")

        try:
            event_type = AuthEventType(event_type_str)
        except ValueError as e:
            raise ValueError(f"Invalid event_type: {event_type_str}") from e

        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        elif timestamp is None:
            timestamp = datetime.now(timezone.utc)

        return cls(
            event_type=event_type,
            principal_id=data.get("principal_id"),
            provider=data.get("provider", "unknown"),
            timestamp=timestamp,
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
            request_id=data.get("request_id"),
            session_id=data.get("session_id"),
            success=data.get("success", True),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


# ═══════════════════════════════════════════════════════════════
# EVENT FACTORY FUNCTIONS
# ═══════════════════════════════════════════════════════════════


def login_success_event(
    principal_id: str,
    provider: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthAuditEvent:
    """Create a successful login event."""
    return AuthAuditEvent(
        event_type=AuthEventType.LOGIN_SUCCESS,
        principal_id=principal_id,
        provider=provider,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        session_id=session_id,
        success=True,
        metadata=metadata or {},
    )


def login_failed_event(
    provider: str,
    *,
    principal_id: str | None = None,
    error_code: str = "AUTHENTICATION_FAILED",
    error_message: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthAuditEvent:
    """Create a failed login event."""
    return AuthAuditEvent(
        event_type=AuthEventType.LOGIN_FAILED,
        principal_id=principal_id,
        provider=provider,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        success=False,
        error_code=error_code,
        error_message=error_message,
        metadata=metadata or {},
    )


def logout_event(
    principal_id: str,
    provider: str,
    *,
    ip_address: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthAuditEvent:
    """Create a logout event."""
    return AuthAuditEvent(
        event_type=AuthEventType.LOGOUT,
        principal_id=principal_id,
        provider=provider,
        ip_address=ip_address,
        request_id=request_id,
        session_id=session_id,
        metadata=metadata or {},
    )


def token_refreshed_event(
    principal_id: str,
    provider: str,
    *,
    ip_address: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthAuditEvent:
    """Create a token refreshed event."""
    return AuthAuditEvent(
        event_type=AuthEventType.TOKEN_REFRESHED,
        principal_id=principal_id,
        provider=provider,
        ip_address=ip_address,
        request_id=request_id,
        metadata=metadata or {},
    )


def mfa_verified_event(
    principal_id: str,
    provider: str,
    *,
    method: str = "totp",
    ip_address: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthAuditEvent:
    """Create an MFA verified event."""
    meta = {"method": method}
    if metadata:
        meta.update(metadata)
    return AuthAuditEvent(
        event_type=AuthEventType.MFA_VERIFIED,
        principal_id=principal_id,
        provider=provider,
        ip_address=ip_address,
        request_id=request_id,
        metadata=meta,
    )


def api_key_used_event(
    principal_id: str,
    api_key_id: str,
    api_key_name: str,
    *,
    ip_address: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthAuditEvent:
    """Create an API key used event."""
    meta = {"api_key_id": api_key_id, "api_key_name": api_key_name}
    if metadata:
        meta.update(metadata)
    return AuthAuditEvent(
        event_type=AuthEventType.API_KEY_USED,
        principal_id=principal_id,
        provider="apikey",
        ip_address=ip_address,
        request_id=request_id,
        metadata=meta,
    )


def session_created_event(
    principal_id: str,
    session_id: str,
    provider: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthAuditEvent:
    """Create a session created event."""
    meta = {"session_id": session_id}
    if metadata:
        meta.update(metadata)
    return AuthAuditEvent(
        event_type=AuthEventType.SESSION_CREATED,
        principal_id=principal_id,
        provider=provider,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        session_id=session_id,
        metadata=meta,
    )


def session_destroyed_event(
    principal_id: str,
    session_id: str,
    provider: str,
    *,
    ip_address: str | None = None,
    request_id: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthAuditEvent:
    """Create a session destroyed event."""
    meta = {"session_id": session_id}
    if reason:
        meta["reason"] = reason
    if metadata:
        meta.update(metadata)
    return AuthAuditEvent(
        event_type=AuthEventType.SESSION_DESTROYED,
        principal_id=principal_id,
        provider=provider,
        ip_address=ip_address,
        request_id=request_id,
        session_id=session_id,
        metadata=meta,
    )


__all__: list[str] = [
    "AuthEventType",
    "AuthAuditEvent",
    "login_success_event",
    "login_failed_event",
    "logout_event",
    "token_refreshed_event",
    "mfa_verified_event",
    "api_key_used_event",
    "session_created_event",
    "session_destroyed_event",
]
