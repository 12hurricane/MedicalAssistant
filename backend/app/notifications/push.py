import logging
from app.models.types import utcnow
from app.notifications.base import BaseNotificationProvider, NotificationMessage, NotificationResult

logger = logging.getLogger(__name__)


class PushNotificationProvider(BaseNotificationProvider):
    """Push notification provider (e.g. Firebase Cloud Messaging / APNs)."""

    @property
    def channel_name(self) -> str:
        return "PUSH"

    async def send(self, message: NotificationMessage) -> NotificationResult:
        formatted = message.format_text()
        print(f"[PushNotification] Push to token '{message.recipient_address or 'dev-device'}': {formatted}")
        return NotificationResult(
            success=True,
            channel="PUSH",
            external_id=f"push-{message.reminder_id}",
            delivered_at=utcnow(),
        )
