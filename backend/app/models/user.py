from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.patient import Patient

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hashed_password: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default='PATIENT')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(default=1, server_default=text("1"), nullable=False)

    # Relationships
    patient: Mapped["Patient"] = relationship(
        "Patient", 
        back_populates="user", 
        uselist=False,
        cascade="all, delete-orphan"
    )
