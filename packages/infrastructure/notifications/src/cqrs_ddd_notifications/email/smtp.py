"""SMTP email implementation."""

from __future__ import annotations

import email.message
import email.policy
import logging

from ..delivery import DeliveryRecord, NotificationChannel, RenderedNotification
from ..ports.sender import INotificationSender

logger = logging.getLogger(__name__)


class SmtpEmailSender(INotificationSender):
    """
    Async SMTP email sender using aiosmtplib.
    """

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout: float = 10.0,
        from_email: str | None = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.timeout = timeout
        self.from_email = from_email

    async def send(
        self,
        recipient: str,
        content: RenderedNotification,
        channel: NotificationChannel,
        metadata: dict[str, object] | None = None,
    ) -> DeliveryRecord:
        if channel != NotificationChannel.EMAIL:
            raise ValueError(f"SmtpEmailSender does not support {channel}")

        from_addr = (metadata or {}).get("from_email") or self.from_email
        if not from_addr:
            raise ValueError("Sender email (from_email) is required.")

        # Lazy import of aiosmtplib
        try:
            import aiosmtplib
        except ImportError as e:
            raise ImportError(
                "aiosmtplib is required for SmtpEmailSender. "
                "Install with: pip install 'cqrs-ddd-notifications[smtp]'"
            ) from e

        try:
            # Build email message
            message = email.message.EmailMessage(policy=email.policy.default)
            message["To"] = recipient
            message["From"] = from_addr
            if content.subject:
                message["Subject"] = content.subject

            if content.body_html:
                # Multipart with both text and HTML
                message.set_content(content.body_text, subtype="plain", charset="utf-8")
                message.add_alternative(content.body_html, subtype="html", charset="utf-8")
            else:
                message.set_content(content.body_text, charset="utf-8")

            # Add attachments
            for attachment in content.attachments or []:
                message.add_attachment(
                    attachment.content,
                    maintype=attachment.mimetype.split("/")[0],
                    subtype=attachment.mimetype.split("/")[1],
                    filename=attachment.filename,
                )

            # Send via SMTP
            async with aiosmtplib.SMTP(
                hostname=self.host,
                port=self.port,
                timeout=self.timeout,
            ) as smtp:
                if self.use_tls:
                    await smtp.starttls()
                if self.username and self.password:
                    await smtp.login(self.username, self.password)

                await smtp.send_message(message)

                logger.info(f"Email sent to {recipient} via SMTP")
                return DeliveryRecord.sent(recipient, channel, provider_id="smtp")

        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {str(e)}")
            return DeliveryRecord.failed(recipient, channel, error=str(e))
