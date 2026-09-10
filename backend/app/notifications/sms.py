import logging
from app.models.types import utcnow
from app.notifications.base import BaseNotificationProvider, NotificationMessage, NotificationResult

logger = logging.getLogger(__name__)


class SMSNotificationProvider(BaseNotificationProvider):
    """SMS notification provider (e.g. Twilio, AWS SNS)."""

    @property
    def channel_name(self) -> str:
        return "SMS"

    async def send(self, message: NotificationMessage) -> NotificationResult:
        formatted = message.format_text()
        print(f"[SMSNotification] SMS to '{message.recipient_address or 'phone'}': {formatted}")
        return NotificationResult(
            success=True,
            channel="SMS",
            external_id=f"sms-{message.reminder_id}",
            delivered_at=utcnow(),
        )
