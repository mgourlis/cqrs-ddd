"""Access-control exceptions.

All exceptions inherit from ``DomainError`` (via ``CQRSDDDError`` hierarchy)
so they integrate naturally with the existing error-handling infrastructure.
"""

from __future__ import annotations

from typing import Any

from cqrs_ddd_core import DomainError


class AccessControlError(DomainError):
    """Base for all access-control errors."""

    code: str = "ACCESS_CONTROL_ERROR"
    details: dict[str, Any] = {}  # noqa: RUF012

    def __init__(
        self,
        message: str = "Access control error",
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if details is not None:
            self.details = details


class PermissionDeniedError(AccessControlError):
    """Specific access denied — raised by middleware when authorization fails."""

    code: str = "PERMISSION_DENIED"

    def __init__(
        self,
        message: str = "Access denied",
        *,
        resource_type: str | None = None,
        action: str | None = None,
        resource_ids: list[str] | None = None,
        reason: str = "Access denied",
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.resource_type = resource_type
        self.action = action
        self.resource_ids = resource_ids
        self.reason = reason
        super().__init__(
            message or reason,
            code=code,
            details=details
            or {
                "resource_type": resource_type,
                "action": action,
                "resource_ids": resource_ids,
            },
        )


class InsufficientRoleError(AccessControlError):
    """Principal lacks required role — raised by ``@requires_role``."""

    code: str = "INSUFFICIENT_ROLE"

    def __init__(
        self,
        required_role: str,
        *,
        message: str | None = None,
    ) -> None:
        self.required_role = required_role
        super().__init__(
            message or f"Insufficient role: {required_role}",
            details={"required_role": required_role},
        )


class ACLError(AccessControlError):
    """ACL operation failure — raised by priority event handlers."""

    code: str = "ACL_ERROR"


class ElevationRequiredError(PermissionDeniedError):
    """Step-up authentication required — raised by ``verify_elevation``."""

    code: str = "ELEVATION_REQUIRED"

    def __init__(
        self,
        action: str,
        *,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message or f"Elevation required for action: {action}",
            resource_type="elevation",
            action=action,
            reason="Elevation required for this action",
            code="ELEVATION_REQUIRED",
        )
