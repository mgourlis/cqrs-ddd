"""Access-control commands."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from cqrs_ddd_core import Command


class GrantACL(Command[dict[str, Any]]):
    """Grant access — type-level or resource-level, to principal or role.

    Conditions can be raw ABAC conditions dict or specification_dsl dict.
    """

    resource_type: str
    action: str
    principal_name: str | None = None
    role_name: str | None = None
    resource_id: str | None = None
    conditions: dict[str, Any] | None = None
    specification_dsl: dict[str, Any] | None = None


class RevokeACL(Command[dict[str, Any]]):
    """Revoke access by compound key."""

    resource_type: str
    action: str
    principal_name: str | None = None
    role_name: str | None = None
    resource_id: str | None = None


class SetResourcePublic(Command[dict[str, Any]]):
    """Toggle type-level public access.

    Note: resource-level public (resource_id != None) is NOT yet supported.
    """

    resource_type: str
    is_public: bool = True


class GrantOwnershipACL(Command[dict[str, Any]]):
    """Grant the current user full access to a resource they just created."""

    resource_type: str
    resource_id: str
    actions: list[str] = Field(
        default_factory=lambda: ["read", "write", "delete", "admin"]
    )
