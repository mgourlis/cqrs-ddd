"""Webhook sender with HMAC signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from cqrs_ddd_core.correlation import get_causation_id, get_correlation_id

from ..delivery import DeliveryRecord, NotificationChannel, RenderedNotification
from ..ports.sender import INotificationSender

logger = logging.getLogger(__name__)


class WebhookSender(INotificationSender):
    """
    Generic HTTP POST webhook sender with HMAC-SHA256 signature.

    Webhooks include correlation headers for distributed tracing.
    Signature verification uses constant-time comparison for security.
    """

    def __init__(
        self,
        timeout: float = 10.0,
        user_agent: str = "cqrs-ddd-notifications/0.1.0",
        sign_webhook: bool = True,
        secret: str | None = None,
    ):
        self.timeout = timeout
        self.user_agent = user_agent
        self.sign_webhook = sign_webhook
        self.secret = secret

    async def send(
        self,
        recipient: str,
        content: RenderedNotification,
        channel: NotificationChannel,
        metadata: dict[str, object] | None = None,
    ) -> DeliveryRecord:
        if channel != NotificationChannel.WEBHOOK:
            raise ValueError(f"WebhookSender does not support {channel}")

        # Lazy import of httpx
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx is required for WebhookSender. "
                "Install with: pip install 'cqrs-ddd-notifications[http]'"
            ) from e

        # Build webhook payload
        payload = {
            "recipient": recipient,
            "subject": content.subject or "",
            "body_text": content.body_text,
            "body_html": content.body_html,
            "metadata": metadata or {},
        }

        # Build headers with correlation context
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "X-Correlation-ID": get_correlation_id() or "",
            "X-Causation-ID": get_causation_id() or "",
        }

        # Add HMAC signature if secret is provided
        if self.sign_webhook and self.secret:
            payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            signature = self._calculate_signature(payload_json)
            headers["X-Webhook-Signature"] = signature

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    recipient,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()

                logger.info(f"Webhook sent successfully to {recipient}")
                return DeliveryRecord.sent(
                    recipient, channel, provider_id=response.headers.get("X-Request-ID")
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"Webhook HTTP error: {e.response.status_code} - {e.response.text}")
            return DeliveryRecord.failed(recipient, channel, error=f"HTTP {e.response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send webhook to {recipient}: {str(e)}")
            return DeliveryRecord.failed(recipient, channel, error=str(e))

    def _calculate_signature(self, payload: str) -> str:
        """
        Calculate HMAC-SHA256 signature for webhook payload.

        Uses constant-time comparison for security.
        """
        if self.secret is None:
            # No signature calculated when secret is not set
            return ""
        payload_bytes = payload.encode("utf-8")
        digest = hmac.new(
            key=self.secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    @staticmethod
    def verify_signature(payload: str, signature: str, secret: str) -> bool:
        """
        Verify webhook signature using constant-time comparison.

        Use this in webhook receivers to authenticate incoming webhooks.
        """
        expected = WebhookSender._calculate_payload_signature(payload, secret)

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def _calculate_payload_signature(payload: str, secret: str) -> str:
        """Helper to calculate signature for verification."""
        payload_bytes = payload.encode("utf-8")
        digest = hmac.new(
            key=secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"
