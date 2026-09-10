import abc
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NotificationMessage:
    """Standardized notification payload for medication reminders."""
    patient_id: int
    medicine_name: str
    scheduled_for: datetime
    dose: Optional[str] = None
    instructions: Optional[str] = None
    relation_to_meal: Optional[str] = None
    channel: str = "PUSH"
    recipient_address: Optional[str] = None  # Push token, phone number, etc.
    reminder_id: Optional[int] = None

    def format_text(self) -> str:
        """User-friendly message text."""
        parts = [f"Medication Reminder: Time to take {self.medicine_name}"]
        if self.dose:
            parts.append(f"({self.dose})")
        if self.relation_to_meal:
            parts.append(f"[{self.relation_to_meal.replace('_', ' ').title()}]")
        if self.instructions:
            parts.append(f"— {self.instructions}")
        return " ".join(parts)


@dataclass
class NotificationResult:
    """Result of attempting to deliver a notification."""
    success: bool
    channel: str
    external_id: Optional[str] = None
    error: Optional[str] = None
    delivered_at: Optional[datetime] = None


class BaseNotificationProvider(abc.ABC):
    """Abstract interface for notification delivery channels (Push, SMS, WhatsApp, Mock)."""

    @property
    @abc.abstractmethod
    def channel_name(self) -> str:
        """Name of the channel (e.g. 'PUSH', 'SMS', 'WHATSAPP', 'MOCK')."""
        pass

    @abc.abstractmethod
    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Dispatch the notification to the external delivery provider."""
        pass
