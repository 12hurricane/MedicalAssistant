from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin

class Medication(TimestampMixin, Base):
    __tablename__ = "medications"
    __table_args__ = (
        # A catalogue with duplicate entries makes name -> medication_id resolution
        # ambiguous, which defeats the point of prescribed_medications.medication_id.
        # Brand alone is too strict: the same brand ships in several strengths and
        # forms (tablet vs syrup), so those are part of the natural key.
        # Caveat: SQL treats NULLs as distinct, so this does not catch duplicates
        # where strength and form are both NULL. create_medication guards that case.
        UniqueConstraint(
            "brand_name", "standard_strength", "dosage_form",
            name="uq_medication_brand_strength_form",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    generic_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    drug_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(50), nullable=True)
    standard_strength: Mapped[str | None] = mapped_column(String(50), nullable=True)
    food_interaction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
