"""Email notification providers."""

from __future__ import annotations

import importlib.util

from .smtp import SmtpEmailSender

__all__ = ["SmtpEmailSender"]

# AWS SES optional
if importlib.util.find_spec("aiobotocore") is not None:
    from .ses import SesEmailSender  # noqa: F401

    __all__.append("SesEmailSender")
