"""Tests for audit events."""

from __future__ import annotations

from datetime import UTC

import pytest

from cqrs_ddd_identity.audit.events import (
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


class TestAuthEventType:
    """Test AuthEventType enum."""

    def test_login_values(self) -> None:
        assert AuthEventType.LOGIN_SUCCESS.value == "auth.login.success"
        assert AuthEventType.LOGIN_FAILED.value == "auth.login.failed"
        assert AuthEventType.LOGOUT.value == "auth.logout"

    def test_mfa_values(self) -> None:
        assert AuthEventType.MFA_VERIFIED.value == "auth.mfa.verified"


class TestAuthAuditEvent:
    """Test AuthAuditEvent."""

    def test_success_default(self) -> None:
        ev = AuthAuditEvent(event_type=AuthEventType.LOGIN_SUCCESS, principal_id="u1")
        assert ev.success is True
        assert ev.error_code is None

    def test_failure_sets_error_code(self) -> None:
        ev = AuthAuditEvent(
            event_type=AuthEventType.LOGIN_FAILED,
            success=False,
        )
        assert ev.success is False
        assert ev.error_code == "UNKNOWN_ERROR"

    def test_failure_with_error_code_preserved(self) -> None:
        ev = AuthAuditEvent(
            event_type=AuthEventType.LOGIN_FAILED,
            success=False,
            error_code="INVALID_PASSWORD",
        )
        assert ev.error_code == "INVALID_PASSWORD"

    def test_to_dict(self) -> None:
        ev = AuthAuditEvent(
            event_type=AuthEventType.LOGIN_SUCCESS,
            principal_id="u1",
            provider="keycloak",
        )
        d = ev.to_dict()
        assert d["event_type"] == "auth.login.success"
        assert d["principal_id"] == "u1"
        assert d["provider"] == "keycloak"
        assert d["success"] is True
        assert "timestamp" in d

    def test_from_dict_minimal(self) -> None:
        d = {"event_type": "auth.login.success", "principal_id": "u1"}
        ev = AuthAuditEvent.from_dict(d)
        assert ev.event_type == AuthEventType.LOGIN_SUCCESS
        assert ev.principal_id == "u1"
        assert ev.provider == "unknown"
        assert ev.timestamp is not None

    def test_from_dict_with_timestamp_string(self) -> None:
        d = {
            "event_type": "auth.logout",
            "timestamp": "2024-01-15T12:00:00+00:00",
        }
        ev = AuthAuditEvent.from_dict(d)
        assert ev.timestamp.tzinfo == UTC

    def test_from_dict_missing_event_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing required 'event_type'"):
            AuthAuditEvent.from_dict({})

    def test_from_dict_invalid_event_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid event_type"):
            AuthAuditEvent.from_dict({"event_type": "invalid.type"})


class TestLoginSuccessEvent:
    def test_creates_event(self) -> None:
        ev = login_success_event("u1", "keycloak", ip_address="1.2.3.4")
        assert ev.event_type == AuthEventType.LOGIN_SUCCESS
        assert ev.principal_id == "u1"
        assert ev.provider == "keycloak"
        assert ev.ip_address == "1.2.3.4"
        assert ev.success is True


class TestLoginFailedEvent:
    def test_creates_event(self) -> None:
        ev = login_failed_event("keycloak", error_message="Bad password")
        assert ev.event_type == AuthEventType.LOGIN_FAILED
        assert ev.provider == "keycloak"
        assert ev.success is False
        assert ev.error_message == "Bad password"


class TestLogoutEvent:
    def test_creates_event(self) -> None:
        ev = logout_event("u1", "keycloak", session_id="sess-1")
        assert ev.event_type == AuthEventType.LOGOUT
        assert ev.principal_id == "u1"
        assert ev.session_id == "sess-1"


class TestTokenRefreshedEvent:
    def test_creates_event(self) -> None:
        ev = token_refreshed_event("u1", "keycloak")
        assert ev.event_type == AuthEventType.TOKEN_REFRESHED
        assert ev.principal_id == "u1"


class TestMfaVerifiedEvent:
    def test_creates_event(self) -> None:
        ev = mfa_verified_event("u1", "keycloak", method="totp")
        assert ev.event_type == AuthEventType.MFA_VERIFIED
        assert ev.metadata.get("method") == "totp"


class TestApiKeyUsedEvent:
    def test_creates_event(self) -> None:
        ev = api_key_used_event("u1", "key-id", "My Key", ip_address="10.0.0.1")
        assert ev.event_type == AuthEventType.API_KEY_USED
        assert ev.provider == "apikey"
        assert ev.metadata.get("api_key_id") == "key-id"
        assert ev.metadata.get("api_key_name") == "My Key"


class TestSessionCreatedEvent:
    def test_creates_event(self) -> None:
        ev = session_created_event("u1", "sess-1", "keycloak")
        assert ev.event_type == AuthEventType.SESSION_CREATED
        assert ev.session_id == "sess-1"
        assert ev.metadata.get("session_id") == "sess-1"


class TestSessionDestroyedEvent:
    def test_creates_event(self) -> None:
        ev = session_destroyed_event("u1", "sess-1", "keycloak", reason="logout")
        assert ev.event_type == AuthEventType.SESSION_DESTROYED
        assert ev.metadata.get("reason") == "logout"
