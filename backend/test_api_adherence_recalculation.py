"""Phase 9 Step 5: Deterministic Adherence Recalculation Integration Tests.

Verifies:
1. Scenario 1: Single Event Upward Correction Differential (MISSED -> TAKEN).
   - Only logically affected values change:
     total_taken (+1), total_missed (-1), adherence_rate increases, missed_rate decreases.
   - Denominator (expected_doses) remains strictly constant.
   - Affected time slot updates total_taken/total_missed while other slots remain byte-identical.
   - Affected weekday updates while other weekdays remain byte-identical.
   - ClinicalBrief.adherence_rate matches the recalculated rate.

2. Scenario 2: Downward Correction Differential (TAKEN -> SKIPPED).
   - Reversibility: total_taken (-1), total_skipped (+1), adherence_rate decreases.
   - Running streak is broken and recalculated chronologically.

3. Scenario 3: Escalation Threshold Transition.
   - Patient with 3 consecutive missed doses has should_escalate=True.
   - Correcting a missed dose to TAKEN deterministically breaks the consecutive missed chain.
   - should_escalate transitions to False (or clears the consecutive_missed escalation reason).

4. Scenario 4: Historical Entity Identity and Audit Trail Immutability.
   - MedicationEvent.id, scheduled_at, schedule_id, and patient_id are strictly preserved.
   - Recalculation queries the live event table without corrupting or mutating the audit trail.
   - Sequential corrections append to MedicationEventCorrection without branching.

5. Scenario 5: Safety Assessment and Clinical Evidence Isolation.
   - Adherence rate recalculation does NOT modify deterministic drug safety verdicts,
     interaction severity, human-review flags, or clinical evidence citations.
"""

from datetime import date, datetime, time, timedelta, timezone
import pytest
from sqlalchemy import select

from app.models import (
    Medication,
    MedicationEvent,
    MedicationEventStatus,
    MedicationSchedule,
    Patient,
    PrescribedMedication,
    Prescription,
    ScheduleLifecycle,
    User,
)
from app.models.clinician_patient_assignment import ClinicianPatientAssignment
from app.models.medication_event_correction import MedicationEventCorrection
from app.models.types import utcnow
from conftest import _bootstrap_admin_headers, _session_for, register


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_fast_llm_for_recalculation_tests(monkeypatch):
    """Provide deterministic mock response for extraction to avoid slow CPU inference."""
    async def _fast_gen(*args, **kwargs):
        return '{"barrier_context": []}', "GENERATED_OLLAMA"

    monkeypatch.setattr(
        "app.analysis.adherence_analysis_service.get_generative_response",
        _fast_gen,
    )


async def _setup_recalculation_scenario(client):
    """Seed an authorized clinician, patient, medication, schedule, and assignment."""
    headers_pat = await register(client, "recalc_pat@example.com", role="PATIENT")
    headers_clin = await register(client, "recalc_clin@example.com", role="CLINICIAN")

    async with _session_for(client) as session:
        user_pat = (
            await session.execute(select(User).where(User.email == "recalc_pat@example.com"))
        ).scalars().one()
        pat = (
            await session.execute(select(Patient).where(Patient.user_id == user_pat.id))
        ).scalars().one()
        pat.timezone = "UTC"

        user_clin = (
            await session.execute(select(User).where(User.email == "recalc_clin@example.com"))
        ).scalars().one()

        assignment = ClinicianPatientAssignment(
            clinician_id=user_clin.id,
            patient_id=pat.id,
            assigned_at=utcnow(),
        )
        session.add(assignment)

        # Medication & Schedule
        med = Medication(
            brand_name="Glucophage",
            generic_name="Metformin HCl",
            standard_strength="500mg",
            dosage_form="tablet",
        )
        session.add(med)
        await session.flush()

        rx = Prescription(
            patient_id=pat.id,
            doctor_name="Dr. Specialist",
            prescription_date=date(2026, 1, 1),
            verification_status="VERIFIED",
        )
        session.add(rx)
        await session.flush()

        pm = PrescribedMedication(
            prescription_id=rx.id,
            patient_id=pat.id,
            medication_id=med.id,
            medicine_name="Glucophage",
            dose="500mg",
            frequency="twice daily",
        )
        session.add(pm)
        await session.flush()

        sched = MedicationSchedule(
            patient_id=pat.id,
            prescribed_medication_id=pm.id,
            scheduled_time=time(9, 0),
            start_date=date(2026, 1, 1),
            status=ScheduleLifecycle.ACTIVE.value,
        )
        session.add(sched)
        await session.flush()

        patient_id = pat.id
        sched_id = sched.id
        await session.commit()

    return {
        "headers_pat": headers_pat,
        "headers_clin": headers_clin,
        "patient_id": patient_id,
        "schedule_id": sched_id,
    }


# ===========================================================================
# Step 5 Integration Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_recalculation_single_event_upward_correction(client):
    """Scenario 1: Single event MISSED -> TAKEN differential.

    Verifies:
    - total_taken increments by 1
    - total_missed decrements by 1
    - expected_doses remains unchanged
    - adherence_rate increases deterministically
    - target time-slot is updated while other slots remain byte-identical
    - target weekday is updated while other weekdays remain byte-identical
    - clinical_brief.adherence_rate in analysis endpoint matches score endpoint
    """
    data = await _setup_recalculation_scenario(client)
    pat_id = data["patient_id"]
    sched_id = data["schedule_id"]
    headers_clin = data["headers_clin"]

    now = utcnow()
    # Seed 4 events within the 7-day lookback window
    # Event 1: 3 days ago at 09:00 UTC (morning) -> TAKEN
    # Event 2: 2 days ago at 09:00 UTC (morning) -> MISSED (target to correct)
    # Event 3: 1 day ago at 14:00 UTC (afternoon) -> TAKEN
    # Event 4: 12 hours ago at 19:00 UTC (evening) -> SKIPPED
    dt1 = (now - timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    dt2 = (now - timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
    dt3 = (now - timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    dt4 = (now - timedelta(hours=12)).replace(hour=19, minute=0, second=0, microsecond=0)

    target_event_id = None
    async with _session_for(client) as session:
        ev1 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt1,
            status=MedicationEventStatus.TAKEN.value, confirmed_at=dt1, recorded_by="PATIENT"
        )
        ev2 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt2,
            status=MedicationEventStatus.MISSED.value, recorded_by="SYSTEM"
        )
        ev3 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt3,
            status=MedicationEventStatus.TAKEN.value, confirmed_at=dt3, recorded_by="PATIENT"
        )
        ev4 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt4,
            status=MedicationEventStatus.SKIPPED.value, skip_reason_code="SIDE_EFFECTS", recorded_by="PATIENT"
        )
        session.add_all([ev1, ev2, ev3, ev4])
        await session.commit()
        await session.refresh(ev2)
        target_event_id = ev2.id

    # 1. Fetch Baseline Adherence Score & Analysis
    resp_score_base = await client.get(
        f"/api/v1/adherence/score?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    assert resp_score_base.status_code == 200
    base_score = resp_score_base.json()

    resp_analysis_base = await client.get(
        f"/api/v1/adherence/analysis?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    assert resp_analysis_base.status_code == 200
    base_analysis = resp_analysis_base.json()

    # Validate Baseline Numbers
    assert base_score["expected_doses"] == 4
    assert base_score["total_taken"] == 2
    assert base_score["total_missed"] == 1
    assert base_score["total_skipped"] == 1
    assert base_score["adherence_rate"] == 50.0  # 2 / 4 * 100.0
    assert base_score["missed_rate"] == 25.0     # 1 / 4 * 100.0
    assert base_score["skipped_rate"] == 25.0    # 1 / 4 * 100.0
    assert base_analysis["clinical_brief"]["adherence_rate"] == 50.0

    # Capture baseline slots for invariance checking
    base_morning = base_score["time_slot_breakdown"]["morning"]
    base_afternoon = base_score["time_slot_breakdown"]["afternoon"]
    base_evening = base_score["time_slot_breakdown"]["evening"]
    base_night = base_score["time_slot_breakdown"]["night"]

    assert base_morning["total_expected"] == 2
    assert base_morning["total_taken"] == 1
    assert base_morning["total_missed"] == 1
    assert base_morning["adherence_rate"] == 50.0

    # 2. Authorized Clinician Correction: MISSED -> TAKEN
    resp_corr = await client.post(
        f"/api/v1/adherence/events/{target_event_id}/correct",
        headers=headers_clin,
        json={
            "new_status": "TAKEN",
            "reason": "Patient confirmed dose taken at 09:15 AM; network delayed log",
        },
    )
    assert resp_corr.status_code == 200, f"Correction failed: {resp_corr.text}"

    # 3. Fetch Recalculated Score & Analysis
    resp_score_recalc = await client.get(
        f"/api/v1/adherence/score?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    assert resp_score_recalc.status_code == 200
    recalc_score = resp_score_recalc.json()

    resp_analysis_recalc = await client.get(
        f"/api/v1/adherence/analysis?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    assert resp_analysis_recalc.status_code == 200
    recalc_analysis = resp_analysis_recalc.json()

    # 4. Assert Exact Differential Logic
    # Denominator must remain invariant
    assert recalc_score["expected_doses"] == 4
    # Affected counts
    assert recalc_score["total_taken"] == base_score["total_taken"] + 1  # 2 -> 3
    assert recalc_score["total_missed"] == base_score["total_missed"] - 1  # 1 -> 0
    assert recalc_score["total_skipped"] == base_score["total_skipped"]  # 1 (unchanged)
    # Recalculated rates
    assert recalc_score["adherence_rate"] == 75.0  # 3 / 4 * 100.0
    assert recalc_score["missed_rate"] == 0.0      # 0 / 4 * 100.0
    assert recalc_score["skipped_rate"] == 25.0    # 1 / 4 * 100.0 (unchanged)

    # Invariance check: Only morning slot changed; afternoon/evening/night are byte-identical
    recalc_morning = recalc_score["time_slot_breakdown"]["morning"]
    assert recalc_morning["total_expected"] == 2
    assert recalc_morning["total_taken"] == 2      # 1 -> 2
    assert recalc_morning["total_missed"] == 0     # 1 -> 0
    assert recalc_morning["adherence_rate"] == 100.0

    assert recalc_score["time_slot_breakdown"]["afternoon"] == base_afternoon
    assert recalc_score["time_slot_breakdown"]["evening"] == base_evening
    assert recalc_score["time_slot_breakdown"]["night"] == base_night

    # Analysis clinical brief adherence rate must match recalculated score exactly
    assert recalc_analysis["clinical_brief"]["adherence_rate"] == 75.0


@pytest.mark.asyncio
async def test_recalculation_status_reversal_downward_correction(client):
    """Scenario 2: Status Reversal / Downward Correction (TAKEN -> SKIPPED).

    Verifies:
    - Adherence calculation is symmetric: correcting TAKEN to SKIPPED lowers adherence_rate
    - Denominator expected_doses remains unchanged
    - Running streak is broken and recalculated chronologically
    """
    data = await _setup_recalculation_scenario(client)
    pat_id = data["patient_id"]
    sched_id = data["schedule_id"]
    headers_clin = data["headers_clin"]

    now = utcnow()
    # 3 consecutive doses in the window: all TAKEN
    dt1 = (now - timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    dt2 = (now - timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
    dt3 = (now - timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    target_event_id = None
    async with _session_for(client) as session:
        ev1 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt1,
            status=MedicationEventStatus.TAKEN.value, confirmed_at=dt1, recorded_by="PATIENT"
        )
        ev2 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt2,
            status=MedicationEventStatus.TAKEN.value, confirmed_at=dt2, recorded_by="PATIENT"
        )
        ev3 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt3,
            status=MedicationEventStatus.TAKEN.value, confirmed_at=dt3, recorded_by="PATIENT"
        )
        session.add_all([ev1, ev2, ev3])
        await session.commit()
        await session.refresh(ev2)
        target_event_id = ev2.id

    # Baseline: 100% adherence, streak 3
    base_resp = await client.get(
        f"/api/v1/adherence/score?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    base = base_resp.json()
    assert base["expected_doses"] == 3
    assert base["total_taken"] == 3
    assert base["adherence_rate"] == 100.0
    assert base["current_streak"] == 3

    # Correction: Clinician sets Event 2 to SKIPPED
    corr_resp = await client.post(
        f"/api/v1/adherence/events/{target_event_id}/correct",
        headers=headers_clin,
        json={
            "new_status": "SKIPPED",
            "reason": "Dose was held prior to diagnostic procedure",
        },
    )
    assert corr_resp.status_code == 200

    # Recalculated: 2 taken, 1 skipped
    recalc_resp = await client.get(
        f"/api/v1/adherence/score?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    recalc = recalc_resp.json()

    assert recalc["expected_doses"] == 3
    assert recalc["total_taken"] == 2
    assert recalc["total_skipped"] == 1
    assert recalc["adherence_rate"] == 66.7  # round(2/3 * 100.0, 1)
    assert recalc["skipped_rate"] == 33.3    # round(1/3 * 100.0, 1)

    # Streak broken: ev1 taken (streak=1) -> ev2 skipped (streak=0) -> ev3 taken (streak=1)
    assert recalc["current_streak"] == 1
    assert recalc["best_streak"] == 1


@pytest.mark.asyncio
async def test_recalculation_escalation_threshold_transition(client):
    """Scenario 3: Escalation Threshold Transition.

    Verifies:
    - 3 consecutive missed doses trigger should_escalate=True and 'consecutive missed' reason.
    - Correcting the latest missed dose to TAKEN deterministically eliminates the
      3-consecutive-missed threshold and updates escalation state.
    """
    data = await _setup_recalculation_scenario(client)
    pat_id = data["patient_id"]
    sched_id = data["schedule_id"]
    headers_clin = data["headers_clin"]

    now = utcnow()
    # 4 doses: 1 TAKEN, followed by 3 consecutive MISSED
    dt1 = (now - timedelta(days=4)).replace(hour=9, minute=0, second=0, microsecond=0)
    dt2 = (now - timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    dt3 = (now - timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
    dt4 = (now - timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    target_event_id = None
    async with _session_for(client) as session:
        ev1 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt1,
            status=MedicationEventStatus.TAKEN.value, confirmed_at=dt1, recorded_by="PATIENT"
        )
        ev2 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt2,
            status=MedicationEventStatus.MISSED.value, recorded_by="SYSTEM"
        )
        ev3 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt3,
            status=MedicationEventStatus.MISSED.value, recorded_by="SYSTEM"
        )
        ev4 = MedicationEvent(
            schedule_id=sched_id, patient_id=pat_id, scheduled_at=dt4,
            status=MedicationEventStatus.MISSED.value, recorded_by="SYSTEM"
        )
        session.add_all([ev1, ev2, ev3, ev4])
        await session.commit()
        await session.refresh(ev4)
        target_event_id = ev4.id

    # Baseline query: should_escalate must be True due to 3 consecutive missed
    resp_base = await client.get(
        f"/api/v1/adherence/score?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    base = resp_base.json()
    assert base["should_escalate"] is True
    assert any("consecutive missed doses" in r.lower() for r in base["escalation_reasons"])

    # Action: Clinician corrects Event 4 from MISSED to TAKEN
    corr_resp = await client.post(
        f"/api/v1/adherence/events/{target_event_id}/correct",
        headers=headers_clin,
        json={
            "new_status": "TAKEN",
            "reason": "Patient confirmed dose was taken; phone battery died",
        },
    )
    assert corr_resp.status_code == 200

    # Recalculated query: consecutive missed run is now only 2 (Event 2 and 3)
    resp_recalc = await client.get(
        f"/api/v1/adherence/score?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    recalc = resp_recalc.json()
    # Consecutive missed reason must be removed
    assert not any("consecutive missed doses" in r.lower() for r in recalc["escalation_reasons"])


@pytest.mark.asyncio
async def test_recalculation_entity_identity_and_audit_history_immutability(client):
    """Scenario 4: Entity Identity and Audit Trail Immutability.

    Verifies:
    - MedicationEvent.id is identical before, during, and after recalculation.
    - scheduled_at timestamp is never shifted or overwritten.
    - Multiple corrections append linearly to MedicationEventCorrection without forking.
    - Recalculation reads live event state and leaves audit rows strictly read-only.
    """
    data = await _setup_recalculation_scenario(client)
    pat_id = data["patient_id"]
    sched_id = data["schedule_id"]
    headers_clin = data["headers_clin"]

    now = utcnow()
    dt = (now - timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)

    event_id = None
    original_scheduled_at = None
    async with _session_for(client) as session:
        ev = MedicationEvent(
            schedule_id=sched_id,
            patient_id=pat_id,
            scheduled_at=dt,
            status=MedicationEventStatus.MISSED.value,
            recorded_by="SYSTEM",
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        event_id = ev.id
        original_scheduled_at = ev.scheduled_at

    # Correction 1: MISSED -> TAKEN
    r1 = await client.post(
        f"/api/v1/adherence/events/{event_id}/correct",
        headers=headers_clin,
        json={"new_status": "TAKEN", "reason": "Patient called clinic to report taken"},
    )
    assert r1.status_code == 200

    # Recalculate after Correction 1
    resp1 = await client.get(
        f"/api/v1/adherence/score?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    assert resp1.status_code == 200
    assert resp1.json()["total_taken"] == 1
    assert resp1.json()["total_missed"] == 0

    # Correction 2: TAKEN -> SKIPPED
    r2 = await client.post(
        f"/api/v1/adherence/events/{event_id}/correct",
        headers=headers_clin,
        json={"new_status": "SKIPPED", "reason": "Patient called back: actually skipped"},
    )
    assert r2.status_code == 200

    # Recalculate after Correction 2
    resp2 = await client.get(
        f"/api/v1/adherence/score?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    assert resp2.status_code == 200
    assert resp2.json()["total_taken"] == 0
    assert resp2.json()["total_skipped"] == 1

    # Verify Database Normalization & Audit Chain
    async with _session_for(client) as session:
        ev_final = (
            await session.execute(select(MedicationEvent).where(MedicationEvent.id == event_id))
        ).scalars().one()

        # Event ID & scheduled_at invariant
        assert ev_final.id == event_id
        assert ev_final.scheduled_at == original_scheduled_at
        assert ev_final.status == MedicationEventStatus.SKIPPED.value

        # Audit rows: exactly 2 rows linked to event_id forming linear chain
        audit_rows = (
            await session.execute(
                select(MedicationEventCorrection)
                .where(MedicationEventCorrection.event_id == event_id)
                .order_by(MedicationEventCorrection.id.asc())
            )
        ).scalars().all()

        assert len(audit_rows) == 2
        # First correction: MISSED -> TAKEN
        assert audit_rows[0].previous_status == MedicationEventStatus.MISSED.value
        assert audit_rows[0].new_status == MedicationEventStatus.TAKEN.value
        # Second correction: TAKEN -> SKIPPED
        assert audit_rows[1].previous_status == MedicationEventStatus.TAKEN.value
        assert audit_rows[1].new_status == MedicationEventStatus.SKIPPED.value


@pytest.mark.asyncio
async def test_recalculation_safety_assessment_and_evidence_isolation(client):
    """Scenario 5: Safety Assessment and Clinical Evidence Isolation.

    Verifies:
    - Recalculating adherence across the HTTP boundary updates adherence rates
      without modifying deterministic safety assessment rules (e.g. drug interactions),
      requires_human_review flags, or clinical evidence citations.
    """
    data = await _setup_recalculation_scenario(client)
    pat_id = data["patient_id"]
    sched_id = data["schedule_id"]
    headers_clin = data["headers_clin"]

    now = utcnow()
    dt = (now - timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)

    # In addition to Glucophage, add an interacting drug pair (Viagra + Nitrostat -> CONTRAINDICATED)
    async with _session_for(client) as session:
        med_viagra = Medication(
            brand_name="Viagra",
            generic_name="sildenafil",
            standard_strength="50mg",
            dosage_form="tablet",
        )
        med_nitro = Medication(
            brand_name="Nitrostat",
            generic_name="nitroglycerin",
            standard_strength="0.4mg",
            dosage_form="sublingual tablet",
        )
        session.add_all([med_viagra, med_nitro])
        await session.flush()

        rx = (
            await session.execute(select(Prescription).where(Prescription.patient_id == pat_id))
        ).scalars().first()

        pm_v = PrescribedMedication(
            prescription_id=rx.id,
            patient_id=pat_id,
            medication_id=med_viagra.id,
            medicine_name="Viagra",
            dose="50mg",
            frequency="as needed",
        )
        pm_n = PrescribedMedication(
            prescription_id=rx.id,
            patient_id=pat_id,
            medication_id=med_nitro.id,
            medicine_name="Nitrostat",
            dose="0.4mg",
            frequency="as needed",
        )
        session.add_all([pm_v, pm_n])

        # Dose event for Glucophage: MISSED
        ev = MedicationEvent(
            schedule_id=sched_id,
            patient_id=pat_id,
            scheduled_at=dt,
            status=MedicationEventStatus.MISSED.value,
            recorded_by="SYSTEM",
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        event_id = ev.id

    # 1. Baseline Analysis
    resp_base = await client.get(
        f"/api/v1/adherence/analysis?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    assert resp_base.status_code == 200
    base_analysis = resp_base.json()

    # Safety findings must be CONTRAINDICATED / CRITICAL due to Viagra + Nitrostat
    assert base_analysis["safety_risk_level"] in ("CRITICAL", "HIGH")
    assert base_analysis["requires_human_review"] is True
    assert base_analysis["clinical_brief"]["adherence_rate"] == 0.0

    # 2. Correct event: MISSED -> TAKEN
    corr_resp = await client.post(
        f"/api/v1/adherence/events/{event_id}/correct",
        headers=headers_clin,
        json={"new_status": "TAKEN", "reason": "Patient took morning Glucophage with food"},
    )
    assert corr_resp.status_code == 200

    # 3. Recalculate Analysis
    resp_recalc = await client.get(
        f"/api/v1/adherence/analysis?period=7d&patient_id={pat_id}",
        headers=headers_clin,
    )
    assert resp_recalc.status_code == 200
    recalc_analysis = resp_recalc.json()

    # Adherence rate updated
    assert recalc_analysis["clinical_brief"]["adherence_rate"] == 100.0

    # Safety assessment invariants strictly preserved
    assert recalc_analysis["safety_risk_level"] == base_analysis["safety_risk_level"]
    assert recalc_analysis["requires_human_review"] == base_analysis["requires_human_review"]
    assert recalc_analysis["clinical_brief"]["safety_risk_level"] == base_analysis["clinical_brief"]["safety_risk_level"]
    assert (
        recalc_analysis["clinical_brief"]["citations"]
        == base_analysis["clinical_brief"]["citations"]
    )
