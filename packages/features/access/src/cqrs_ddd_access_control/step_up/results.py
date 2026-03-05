"""Result models for step-up authentication commands."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GrantTemporaryElevationResult(BaseModel):
    """Result of :class:`~.commands.GrantTemporaryElevation`."""

    success: bool
    user_id: str
    action: str
    ttl_seconds: int
    expires_at: datetime | None = None
    message: str = ""


class RevokeElevationResult(BaseModel):
    """Result of :class:`~.commands.RevokeElevation`."""

    success: bool
    user_id: str
    reason: str = "completed"
    message: str = ""


class ResumeSensitiveOperationResult(BaseModel):
    """Result of :class:`~.commands.ResumeSensitiveOperation`."""

    success: bool
    operation_id: str
    resumed: bool = False
    message: str = ""
