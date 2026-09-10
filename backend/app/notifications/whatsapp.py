import logging
from app.models.types import utcnow
from app.notifications.base import BaseNotificationProvider, NotificationMessage, NotificationResult

logger = logging.getLogger(__name__)


class WhatsAppNotificationProvider(BaseNotificationProvider):
    """WhatsApp notification provider (e.g. WhatsApp Cloud API / Twilio)."""

    @property
    def channel_name(self) -> str:
        return "WHATSAPP"

    async def send(self, message: NotificationMessage) -> NotificationResult:
        formatted = message.format_text()
        print(f"[WhatsAppNotification] WhatsApp to '{message.recipient_address or 'phone'}': {formatted}")
        return NotificationResult(
            success=True,
            channel="WHATSAPP",
            external_id=f"wa-{message.reminder_id}",
            delivered_at=utcnow(),
        )
