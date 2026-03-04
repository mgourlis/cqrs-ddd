"""Elevation verification — step-up authentication check."""

from __future__ import annotations

from typing import Literal

from cqrs_ddd_identity import get_access_token

from .exceptions import ElevationRequiredError
from .ports import IAuthorizationPort


async def verify_elevation(
    authorization_port: IAuthorizationPort,
    action: str,
    on_fail: Literal["raise", "return"] = "raise",
) -> bool:
    """Check if the current principal has elevation for the given action.

    Uses the ``"elevation"`` resource type in the ABAC engine.

    Parameters
    ----------
    authorization_port:
        Runtime authorization port.
    action:
        The action requiring elevation (e.g., ``"delete_tenant"``).
    on_fail:
        ``"raise"`` — raise ``ElevationRequiredError`` if not elevated.
        ``"return"`` — return ``False`` if not elevated.
    """
    access_token = get_access_token()
    result = await authorization_port.check_access(
        access_token,
        resource_type="elevation",
        action=action,
    )
    if not result:
        if on_fail == "raise":
            raise ElevationRequiredError(action=action)
        return False
    return True
