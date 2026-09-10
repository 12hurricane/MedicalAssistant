"""
Adherence Calculation Service

Deterministic service for calculating medication adherence metrics, streaks,
time-of-day patterns, day-of-week trends, and clinical escalation triggers.

The Adherence Analysis Service (app/analysis/) is layered on TOP of these structured
metrics to compose patient explanations and clinician briefs. That layer is currently
deterministic template composition, NOT an LLM — no model call exists anywhere in this
codebase yet. The math is executed here, reliably and reproducibly, and stays here even
once a generative layer is added above it.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.medication_event import MedicationEvent, MedicationEventStatus
from app.models.patient import Patient
from app.models.types import utcnow

logger = logging.getLogger(__name__)


@dataclass
class TimeSlotMetrics:
    total_expected: int = 0
    total_taken: int = 0
    total_missed: int = 0
    total_skipped: int = 0

    @property
    def adherence_rate(self) -> Optional[float]:
        """None when this slot has no expected doses. See :class:`AdherenceMetrics`."""
        if self.total_expected == 0:
            return None
        return round((self.total_taken / self.total_expected) * 100.0, 1)


@dataclass
class DayOfWeekMetrics:
    day_name: str
    total_expected: int = 0
    total_taken: int = 0

    @property
    def adherence_rate(self) -> Optional[float]:
        """None when nothing was expected on this weekday in the window.

        Most patients will have several of these on any short window — a 7-day period
        starting mid-week still has every weekday in the list — so this is the common
        case, not an edge case.
        """
        if self.total_expected == 0:
            return None
        return round((self.total_taken / self.total_expected) * 100.0, 1)


@dataclass
class AdherenceMetrics:
    """Comprehensive adherence metrics payload.

    The three rate fields are None when ``expected_doses == 0``, and callers must
    handle that rather than assume a float. They used to be 100.0 / 0.0 / 0.0, which
    is arithmetically defensible — zero of zero doses were missed — and clinically
    wrong: it reports a patient with no medication history as perfectly adherent. The
    distinction matters most for exactly the patients where it was wrong, since a
    newly enrolled patient is the one a clinician has least other information about.

    A null rate means "not measurable from this window", which is a different
    statement from any number, and the only honest one to make with no denominator.
    """
    patient_id: int
    period: str
    period_start: date
    period_end: date
    expected_doses: int
    total_taken: int
    total_missed: int
    total_skipped: int
    total_snoozed: int
    adherence_rate: Optional[float]
    missed_rate: Optional[float]
    skipped_rate: Optional[float]
    current_streak: int
    best_streak: int
    time_slot_breakdown: Dict[str, TimeSlotMetrics]
    day_of_week_breakdown: List[DayOfWeekMetrics]
    trend: str
    detected_patterns: List[str]
    should_escalate: bool
    escalation_reasons: List[str]
    # Raw missed events — exposed so barrier classifier can read patient skip_reason.
    # These are the actual ORM objects from the calculation window.
    missed_events: List = field(default_factory=list)
    # Every non-taken event carrying a patient-supplied reason, structured or free
    # text, regardless of status.
    #
    # This exists because ``missed_events`` filters status == MISSED, while a skip
    # reason is by definition recorded on a SKIPPED event. The barrier classifier read
    # only ``missed_events``, so a patient who tapped "Skip this dose" and chose
    # "Side effects" produced a reason that nothing downstream could ever see. No real
    # data was lost (no SKIPPED rows exist yet), but the structured skip-reason UI
    # would have collected evidence into a dead end.
    reasoned_events: List = field(default_factory=list)


def _get_time_slot_name(hour: int) -> str:
    """Classify local 24-hour clock into human clinical slots."""
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"


def rate_below(rate: Optional[float], threshold: float) -> bool:
    """True when a *measurable* rate is under ``threshold``.

    A null rate is not below anything. With no expected doses there is no rate to
    compare, and treating the absence as a low number would escalate every patient who
    has not logged a dose yet — the mirror image of the bug where absence was treated
    as 100%.

    This exists as one shared function rather than as an ``is not None`` check at each
    of the eight comparison sites across this module, ``barrier_classifier`` and
    ``adherence_analysis_service``. Several of those sites are currently safe only
    because an adjacent ``total_expected >= 3`` test happens to run first and Python
    short-circuits; that is a property of statement order, which reordering silently
    breaks into a TypeError. In ``safety_assessment`` such a TypeError would have been
    swallowed by a bare ``except Exception``, quietly removing adherence from the
    safety assessment for everyone.
    """
    return rate is not None and rate < threshold


def rate_at_least(rate: Optional[float], threshold: float) -> bool:
    """True when a measurable rate is at or above ``threshold``. Null is not."""
    return rate is not None and rate >= threshold


def rate_at_most(rate: Optional[float], threshold: float) -> bool:
    """True when a measurable rate is at or below ``threshold``. Null is not."""
    return rate is not None and rate <= threshold


async def calculate_adherence_score(
    session: AsyncSession,
    patient_id: int,
    days: int = 7,
) -> AdherenceMetrics:
    """
    Calculate deterministic adherence metrics for a patient over the given lookback window.
    
    Expected denominator = TAKEN + MISSED + SKIPPED (excludes future / cancelled / unlogged).
    Evaluates times against the patient's local timezone.
    """
    # 1. Fetch Patient for timezone context
    patient = await session.get(Patient, patient_id)
    try:
        tz = ZoneInfo(patient.timezone if patient and patient.timezone else "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    now_utc = utcnow()
    now_local = now_utc.astimezone(tz)
    period_end = now_local.date()
    period_start = period_end - timedelta(days=days - 1)

    start_local_dt = datetime.combine(period_start, time.min, tzinfo=tz)
    end_local_dt = datetime.combine(period_end, time.max, tzinfo=tz)
    start_utc = start_local_dt.astimezone(timezone.utc)
    end_utc = end_local_dt.astimezone(timezone.utc)

    # 2. Fetch all medication events in the window
    stmt = (
        select(MedicationEvent)
        .where(
            and_(
                MedicationEvent.patient_id == patient_id,
                MedicationEvent.scheduled_at >= start_utc,
                MedicationEvent.scheduled_at <= end_utc,
            )
        )
        .order_by(MedicationEvent.scheduled_at.asc())
    )
    result = await session.execute(stmt)
    events = result.scalars().all()

    # 3. Aggregate totals
    total_taken = sum(1 for e in events if e.status == MedicationEventStatus.TAKEN.value)
    total_missed = sum(1 for e in events if e.status == MedicationEventStatus.MISSED.value)
    total_skipped = sum(1 for e in events if e.status == MedicationEventStatus.SKIPPED.value)
    total_snoozed = sum(1 for e in events if e.status == MedicationEventStatus.SNOOZED.value)

    # Expected doses = TAKEN + MISSED + SKIPPED
    expected_doses = total_taken + total_missed + total_skipped

    if expected_doses == 0:
        # No denominator, so no rate. Not 100% — see AdherenceMetrics.
        adherence_rate = None
        missed_rate = None
        skipped_rate = None
    else:
        adherence_rate = round((total_taken / expected_doses) * 100.0, 1)
        missed_rate = round((total_missed / expected_doses) * 100.0, 1)
        skipped_rate = round((total_skipped / expected_doses) * 100.0, 1)

    # 4. Streak Calculation
    current_streak = 0
    best_streak = 0
    running_streak = 0

    for ev in events:
        if ev.status == MedicationEventStatus.TAKEN.value:
            running_streak += 1
            best_streak = max(best_streak, running_streak)
        elif ev.status in (MedicationEventStatus.MISSED.value, MedicationEventStatus.SKIPPED.value):
            running_streak = 0

    current_streak = running_streak

    # 5. Time Slot Breakdown (calculated in patient local timezone)
    slots = {
        "morning": TimeSlotMetrics(),
        "afternoon": TimeSlotMetrics(),
        "evening": TimeSlotMetrics(),
        "night": TimeSlotMetrics(),
    }

    for ev in events:
        local_ev_dt = ev.scheduled_at.astimezone(tz)
        slot_name = _get_time_slot_name(local_ev_dt.hour)
        metric = slots[slot_name]

        if ev.status == MedicationEventStatus.TAKEN.value:
            metric.total_expected += 1
            metric.total_taken += 1
        elif ev.status == MedicationEventStatus.MISSED.value:
            metric.total_expected += 1
            metric.total_missed += 1
        elif ev.status == MedicationEventStatus.SKIPPED.value:
            metric.total_expected += 1
            metric.total_skipped += 1

    # 6. Day-of-Week Breakdown
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dow_metrics = [DayOfWeekMetrics(day_name=name) for name in day_names]

    for ev in events:
        local_ev_dt = ev.scheduled_at.astimezone(tz)
        weekday_idx = local_ev_dt.weekday()  # 0 = Monday, 6 = Sunday
        dow = dow_metrics[weekday_idx]

        if ev.status in (MedicationEventStatus.TAKEN.value, MedicationEventStatus.MISSED.value, MedicationEventStatus.SKIPPED.value):
            dow.total_expected += 1
            if ev.status == MedicationEventStatus.TAKEN.value:
                dow.total_taken += 1

    # 7. Trend & Pattern Detection
    detected_patterns: List[str] = []

    # Check for time-of-day discrepancies
    for slot_name, metric in slots.items():
        if metric.total_expected >= 3 and rate_below(metric.adherence_rate, 70.0):
            detected_patterns.append(
                f"Patient frequently misses {slot_name} doses ({metric.adherence_rate}% adherence, {metric.total_missed} missed)."
            )

    # Check trend (first half of period vs second half)
    trend = "STABLE"
    if expected_doses == 0:
        # Stated first and explicitly. Nothing below this point can produce a
        # meaningful trend without a rate to compare against.
        trend = "INSUFFICIENT_DATA"
    elif expected_doses >= 6:
        halfway_dt = start_utc + (end_utc - start_utc) / 2
        first_half = [e for e in events if e.scheduled_at < halfway_dt and e.status in ("TAKEN", "MISSED", "SKIPPED")]
        second_half = [e for e in events if e.scheduled_at >= halfway_dt and e.status in ("TAKEN", "MISSED", "SKIPPED")]

        if first_half and second_half:
            r1 = (sum(1 for e in first_half if e.status == "TAKEN") / len(first_half)) * 100.0
            r2 = (sum(1 for e in second_half if e.status == "TAKEN") / len(second_half)) * 100.0

            if r2 < r1 - 15.0:
                trend = "DETERIORATING"
                detected_patterns.append(f"Adherence is deteriorating (dropped from {round(r1, 1)}% to {round(r2, 1)}% in recent days).")
            elif r2 > r1 + 15.0:
                trend = "IMPROVING"
                detected_patterns.append(f"Adherence is improving (rose from {round(r1, 1)}% to {round(r2, 1)}% in recent days).")
    elif expected_doses < 3:
        trend = "INSUFFICIENT_DATA"

    # 8. Deterministic Escalation Evaluation
    escalation_reasons: List[str] = []

    if expected_doses >= 3 and rate_below(adherence_rate, 70.0):
        escalation_reasons.append(f"Overall adherence rate ({adherence_rate}%) is below 70% threshold.")

    # Check consecutive missed doses
    consecutive_missed = 0
    max_consecutive_missed = 0
    for ev in events:
        if ev.status == MedicationEventStatus.MISSED.value:
            consecutive_missed += 1
            max_consecutive_missed = max(max_consecutive_missed, consecutive_missed)
        else:
            consecutive_missed = 0

    if max_consecutive_missed >= 3:
        escalation_reasons.append(f"Patient has {max_consecutive_missed} consecutive missed doses.")

    # Time slot failure
    for slot_name, metric in slots.items():
        if metric.total_expected >= 3 and rate_below(metric.adherence_rate, 50.0):
            escalation_reasons.append(f"Critical adherence breakdown in {slot_name} doses ({metric.adherence_rate}%).")

    if trend == "DETERIORATING" and rate_below(adherence_rate, 75.0):
        escalation_reasons.append("Sharp downward adherence trajectory detected.")

    # No expected doses cannot escalate. Every reason above needs a rate or a count,
    # so this is already true by construction; asserting it keeps that guarantee from
    # depending on the details of eight separate conditions staying correct.
    should_escalate = expected_doses > 0 and len(escalation_reasons) > 0

    return AdherenceMetrics(
        patient_id=patient_id,
        period=f"{days}d",
        period_start=period_start,
        period_end=period_end,
        expected_doses=expected_doses,
        total_taken=total_taken,
        total_missed=total_missed,
        total_skipped=total_skipped,
        total_snoozed=total_snoozed,
        adherence_rate=adherence_rate,
        missed_rate=missed_rate,
        skipped_rate=skipped_rate,
        current_streak=current_streak,
        best_streak=best_streak,
        time_slot_breakdown=slots,
        day_of_week_breakdown=dow_metrics,
        trend=trend,
        detected_patterns=detected_patterns,
        should_escalate=should_escalate,
        escalation_reasons=escalation_reasons,
        missed_events=[e for e in events if e.status == MedicationEventStatus.MISSED.value],
        reasoned_events=[
            e
            for e in events
            if e.status != MedicationEventStatus.TAKEN.value
            and (getattr(e, "skip_reason_code", None) or e.skip_reason)
        ],
    )


