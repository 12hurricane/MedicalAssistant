from typing import Optional
from app.notifications.base import BaseNotificationProvider, NotificationMessage, NotificationResult
from app.notifications.mock import MockNotificationProvider
from app.notifications.push import PushNotificationProvider
from app.notifications.sms import SMSNotificationProvider
from app.notifications.whatsapp import WhatsAppNotificationProvider


class NotificationService:
    """Dispatcher managing notification delivery across multiple channels."""

    def __init__(self):
        self._providers: dict[str, BaseNotificationProvider] = {
            "MOCK": MockNotificationProvider(),
            "PUSH": PushNotificationProvider(),
            "SMS": SMSNotificationProvider(),
            "WHATSAPP": WhatsAppNotificationProvider(),
        }

    def register_provider(self, channel: str, provider: BaseNotificationProvider) -> None:
        self._providers[channel.upper()] = provider

    def get_provider(self, channel: str) -> BaseNotificationProvider:
        return self._providers.get(channel.upper(), self._providers["PUSH"])

    async def send(self, message: NotificationMessage) -> NotificationResult:
        provider = self.get_provider(message.channel)
        return await provider.send(message)


notification_service = NotificationService()
