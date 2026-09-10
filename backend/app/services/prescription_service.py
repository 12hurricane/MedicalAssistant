"""
Prescription Reconciliation Service

Deterministic service -- NOT an LLM agent.

Handles the "doctor corrects a prescription" operation. This exists because the
obvious implementation is silently destructive: replacing
``prescription.medications`` wholesale deletes the old rows, and the
delete-orphan cascade follows

    prescribed_medications -> medication_schedules -> medication_events

so every dose the patient ever logged against that prescription disappears.
Nothing errors; the adherence rate, missed-dose counts, streaks, trends and
clinical brief are all computed from medication_events, so they simply start
reporting a history that never happened.

A correction is therefore modelled as reconciliation, not replacement. Rows are
never deleted -- superseded ones are marked ``is_active = False`` and keep their
schedules and events.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from app.models.prescribed_medication import PrescribedMedication

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from app.models.prescription import Prescription
    from app.schemas.prescription import PrescribedMedicationCreate


def _norm(value: str | None) -> str:
    """Collapse whitespace and case so 'metformin  ' matches 'Metformin'."""
    if value is None:
        return ""
    return " ".join(value.split()).casefold()


def medication_identity(
    medicine_name: str,
    strength: str | None,
    dose: str | None,
    frequency: str,
) -> tuple[str, str, str, str]:
    """
    What makes two prescribed medications "the same line" of a prescription.

    Deliberately includes strength, dose and frequency, not just the drug name.
    Keying on the name alone would let a strength correction update a row that
    already has recorded doses attached, which retroactively relabels them: a
    week of 500mg doses would start claiming to have been 850mg. That is a
    quieter falsification of history than deleting the rows outright, so a
    change to any of these fields produces a new row and retires the old one.

    ``instructions`` and ``duration_days`` are excluded on purpose -- they refine
    an existing line rather than changing which drug was taken at what dose, and
    schedule generation re-derives meal relation and end date from them anyway.
    """
    return (_norm(medicine_name), _norm(strength), _norm(dose), _norm(frequency))


class DuplicateCorrectionError(ValueError):
    """
    Raised when one correction payload lists the same medication line twice.

    Two entries with an identical name, strength, dose and frequency cannot be
    told apart, so honouring both would create an ambiguous duplicate. This is
    almost always a client bug, and it must not be silently deduplicated -- the
    clinician should see that their payload was wrong.
    """

    def __init__(self, medicine_name: str, frequency: str):
        self.medicine_name = medicine_name
        self.frequency = frequency
        super().__init__(
            f"Correction lists {medicine_name!r} ({frequency}) more than once with "
            f"the same strength and dose; the duplicate entries are indistinguishable."
        )


@dataclass(frozen=True)
class MedicationReconciliationResult:
    """Summary of what a correction actually changed."""

    #: Existing lines the correction kept unchanged (instructions/duration refreshed).
    unchanged: int = 0
    #: New lines introduced by the correction, including changed strengths/doses.
    added: int = 0
    #: Previously discontinued lines the correction brought back, history intact.
    reactivated: int = 0
    #: Lines the correction dropped. Retained as inactive, never deleted.
    discontinued: int = 0

    @property
    def active_total(self) -> int:
        return self.unchanged + self.added + self.reactivated


def reconcile_medications(
    prescription: "Prescription",
    corrections: Iterable["PrescribedMedicationCreate"],
) -> MedicationReconciliationResult:
    """
    Bring ``prescription.medications`` in line with a correction payload.

    Requires ``prescription.medications`` to be eagerly loaded. Mutates the
    loaded collection so the session's identity map stays consistent; does not
    flush or commit, so the caller owns the transaction.

    Guarantees:

    1. Nothing is deleted. A dropped or superseded medication is deactivated and
       keeps its schedules, and therefore its medication_events.
    2. A line that is genuinely unchanged keeps its primary key, so its existing
       schedules and history stay attached to it.
    3. Re-adding a previously discontinued line reactivates the original row
       rather than creating a second one, reconnecting it to its own history.

    Raises:
        DuplicateCorrectionError: if the payload lists one line twice.
    """
    buckets: dict[tuple[str, str, str, str], list[PrescribedMedication]] = {}
    for med in prescription.medications:
        key = medication_identity(med.medicine_name, med.strength, med.dose, med.frequency)
        buckets.setdefault(key, []).append(med)

    # Deterministic pick when a bucket holds more than one row (legacy duplicates):
    # prefer an active row, then the lowest id.
    for bucket in buckets.values():
        bucket.sort(key=lambda m: (not m.is_active, m.id or 0))

    unchanged = added = reactivated = discontinued = 0
    seen: set[tuple[str, str, str, str]] = set()

    for correction in corrections:
        data = correction.model_dump()
        key = medication_identity(
            data["medicine_name"], data.get("strength"), data.get("dose"), data["frequency"]
        )
        if key in seen:
            raise DuplicateCorrectionError(data["medicine_name"], data["frequency"])
        seen.add(key)

        bucket = buckets.get(key)
        if bucket:
            target = bucket[0]
            # Refresh only the fields outside the identity key. Overwriting the
            # identity fields would be a no-op by definition, since they matched.
            target.instructions = data.get("instructions")
            target.duration_days = data.get("duration_days")
            if target.is_active:
                unchanged += 1
            else:
                target.is_active = True
                reactivated += 1
            # Retire any legacy duplicates of the same line.
            for extra in bucket[1:]:
                if extra.is_active:
                    extra.is_active = False
                    discontinued += 1
        else:
            prescription.medications.append(
                PrescribedMedication(patient_id=prescription.patient_id, **data)
            )
            added += 1

    # Anything the correction did not mention is no longer prescribed.
    for key, bucket in buckets.items():
        if key in seen:
            continue
        for med in bucket:
            if med.is_active:
                med.is_active = False
                discontinued += 1

    return MedicationReconciliationResult(
        unchanged=unchanged,
        added=added,
        reactivated=reactivated,
        discontinued=discontinued,
    )
