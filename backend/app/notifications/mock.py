import logging
from app.models.types import utcnow
from app.notifications.base import BaseNotificationProvider, NotificationMessage, NotificationResult

logger = logging.getLogger(__name__)


class MockNotificationProvider(BaseNotificationProvider):
    """In-memory notification provider for development and automated testing."""

    def __init__(self):
        self.sent_messages: list[NotificationMessage] = []

    @property
    def channel_name(self) -> str:
        return "MOCK"

    async def send(self, message: NotificationMessage) -> NotificationResult:
        self.sent_messages.append(message)
        formatted = message.format_text()
        print(f"[MockNotificationProvider] Delivered to patient #{message.patient_id}: {formatted}")
        return NotificationResult(
            success=True,
            channel=message.channel,
            external_id=f"mock-{len(self.sent_messages)}",
            delivered_at=utcnow(),
        )

    def clear(self):
        self.sent_messages.clear()
