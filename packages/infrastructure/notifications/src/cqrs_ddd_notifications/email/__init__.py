"""Email notification providers."""

from __future__ import annotations

from .smtp import SmtpEmailSender

__all__ = ["SmtpEmailSender"]

# AWS SES optional
try:
    from .ses import SesEmailSender

    __all__.append("SesEmailSender")
except ImportError:
    pass
