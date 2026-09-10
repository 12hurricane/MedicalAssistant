"""
Regression tests for prescription corrections.

The invariant under test: correcting a prescription must never destroy the
patient's adherence history. Before the reconciliation fix, the corrections path
called ``prescription.medications.clear()``, and the delete-orphan cascade ran
all the way down:

    prescribed_medications -> medication_schedules -> medication_events

so every recorded dose for that prescription vanished. That silently falsifies
adherence rate, missed-dose counts, streaks, trends and the clinical brief --
the metrics are computed from medication_events, so deleting events does not
report an error, it just makes the history a lie.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models.medication_event import MedicationEvent, MedicationEventStatus
from app.models.medication_schedule import MedicationSchedule, ScheduleLifecycle
from app.models.prescribed_medication import PrescribedMedication
from app.models.types import utcnow
from conftest import register

PRESCRIPTION = {
    "doctor_name": "Dr Who",
    "prescription_date": str(date.today()),
    "medications": [
        {"medicine_name": "Metformin", "strength": "500mg", "frequency": "twice daily"},
        {"medicine_name": "Aspirin", "strength": "75mg", "frequency": "once daily"},
    ],
}


def expire(session):
    """
    Drop cached ORM state before reading what a request committed.

    Requests run in their own session. Without this, ``select(Entity)`` returns
    the instance already in this session's identity map with its pre-request
    attribute values, so an assertion can fail (or pass) against state that is
    not in the database. Column selects and aggregates are unaffected, which is
    why only entity reads need it.
    """
    session.expire_all()


async def _setup_verified_prescription(client, session):
    """Patient files a 2-medication prescription; clinician verifies it."""
    patient_h = await register(client, "pat@example.com", "PATIENT")
    clinician_h = await register(client, "doc@example.com", "CLINICIAN")

    r = await client.post("/api/v1/prescriptions", json=PRESCRIPTION, headers=patient_h)
    assert r.status_code == 201, r.text
    presc_id = r.json()["id"]

    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json={"verified": True},
        headers=clinician_h,
    )
    assert r.status_code == 200, r.text
    expire(session)
    # twice daily (2 slots) + once daily (1 slot)
    assert r.json()["scheduling"]["created"] == 3, r.json()["scheduling"]

    return presc_id, patient_h, clinician_h


async def _record_history(session, presc_id):
    """Give every schedule of this prescription one taken dose in the past."""
    rows = await session.execute(
        select(MedicationSchedule)
        .join(PrescribedMedication)
        .where(PrescribedMedication.prescription_id == presc_id)
    )
    schedules = rows.scalars().all()
    assert schedules, "precondition failed: verification generated no schedules"

    for i, sched in enumerate(schedules):
        session.add(
            MedicationEvent(
                schedule_id=sched.id,
                patient_id=sched.patient_id,
                # Aware UTC: UTCDateTime rejects naive datetimes outright.
                scheduled_at=utcnow() - timedelta(days=1, minutes=i),
                status=MedicationEventStatus.TAKEN.value,
                confirmed_at=utcnow() - timedelta(days=1),
            )
        )
    await session.commit()
    return len(schedules)


async def _count(session, model):
    return (await session.execute(select(func.count()).select_from(model))).scalar()


async def test_correction_preserves_adherence_history(client, session):
    """
    The core regression: a correction that drops one medication and changes
    another must leave every recorded dose intact.
    """
    presc_id, _, clinician_h = await _setup_verified_prescription(client, session)
    events_before = await _record_history(session, presc_id)
    assert events_before == 3

    # Clinician corrects: Metformin dose changed, Aspirin removed entirely.
    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json={
            "verified": True,
            "corrections": [
                {
                    "medicine_name": "Metformin",
                    "strength": "500mg",
                    "dose": "1 tablet",
                    "frequency": "three times daily",
                }
            ],
        },
        headers=clinician_h,
    )
    assert r.status_code == 200, r.text
    expire(session)

    events_after = await _count(session, MedicationEvent)
    assert events_after == events_before, (
        f"correction destroyed adherence history: {events_before} events before, "
        f"{events_after} after"
    )


async def test_correction_discontinues_rather_than_deletes(client, session):
    """A medication removed by a correction is retained, flagged inactive."""
    presc_id, _, clinician_h = await _setup_verified_prescription(client, session)
    await _record_history(session, presc_id)

    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json={
            "verified": True,
            "corrections": [
                {"medicine_name": "Metformin", "strength": "500mg", "frequency": "twice daily"}
            ],
        },
        headers=clinician_h,
    )
    assert r.status_code == 200, r.text
    expire(session)

    rows = await session.execute(
        select(PrescribedMedication).where(
            PrescribedMedication.prescription_id == presc_id
        )
    )
    meds = {m.medicine_name: m for m in rows.scalars().all()}

    assert set(meds) == {"Metformin", "Aspirin"}, (
        "the dropped medication row was deleted rather than discontinued"
    )
    assert meds["Metformin"].is_active is True
    assert meds["Aspirin"].is_active is False, (
        "dropped medication is still active, so it would keep firing reminders"
    )


async def test_discontinued_medication_stops_being_scheduled(client, session):
    """
    A discontinued medication must have no active schedules -- otherwise the
    reminder poller keeps dispatching doses the patient is no longer meant to
    take, which is worse than a wrong adherence number.
    """
    presc_id, _, clinician_h = await _setup_verified_prescription(client, session)

    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json={
            "verified": True,
            "corrections": [
                {"medicine_name": "Metformin", "strength": "500mg", "frequency": "twice daily"}
            ],
        },
        headers=clinician_h,
    )
    assert r.status_code == 200, r.text
    expire(session)

    rows = await session.execute(
        select(PrescribedMedication.medicine_name, MedicationSchedule.status)
        .join(MedicationSchedule)
        .where(PrescribedMedication.prescription_id == presc_id)
    )
    by_med: dict[str, list[str]] = {}
    for name, status in rows.all():
        by_med.setdefault(name, []).append(status)

    assert ScheduleLifecycle.ACTIVE.value in by_med.get("Metformin", []), (
        "the kept medication lost its schedules"
    )
    assert ScheduleLifecycle.ACTIVE.value not in by_med.get("Aspirin", []), (
        "the discontinued medication still has active schedules"
    )

    # And the *reason* is recorded, not just the fact. CANCELLED means "the clinician
    # stopped this medication, so these doses were not meant to be taken"; SUPERSEDED
    # would mean "a newer schedule replaced this one", which is a different clinical
    # story and would make the missing doses read as non-adherence. The old boolean
    # could not tell them apart, which is why it was replaced.
    assert set(by_med.get("Aspirin", [])) == {ScheduleLifecycle.CANCELLED.value}, (
        "a discontinued medication's schedules must be CANCELLED, not SUPERSEDED: "
        f"got {by_med.get('Aspirin')}"
    )


async def test_correction_matches_existing_line_despite_case_and_whitespace(
    client, session
):
    """
    A correction that restates a line unchanged must match the existing row, not
    create a near-duplicate. Matching is normalized, so 'metformin  ' is the same
    line as 'Metformin'. Keeping the primary key is what keeps the row's existing
    schedules -- and therefore its history -- attached to it.
    """
    presc_id, _, clinician_h = await _setup_verified_prescription(client, session)

    rows = await session.execute(
        select(PrescribedMedication).where(
            PrescribedMedication.prescription_id == presc_id
        )
    )
    original_ids = {m.medicine_name.casefold(): m.id for m in rows.scalars().all()}

    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json={
            "verified": True,
            "corrections": [
                {"medicine_name": "  metformin ", "strength": "500mg", "frequency": "TWICE DAILY"},
                {"medicine_name": "ASPIRIN", "strength": "75mg", "frequency": "once daily"},
            ],
        },
        headers=clinician_h,
    )
    assert r.status_code == 200, r.text
    expire(session)
    recon = r.json()["reconciliation"]
    assert recon["unchanged"] == 2, recon
    assert recon["added"] == 0, recon
    assert recon["discontinued"] == 0, recon

    rows = await session.execute(
        select(PrescribedMedication).where(
            PrescribedMedication.prescription_id == presc_id
        )
    )
    after = {m.medicine_name.strip().casefold(): m.id for m in rows.scalars().all()}
    assert after == original_ids, "restating a line unchanged created new rows"


async def test_strength_change_supersedes_instead_of_relabelling_history(
    client, session
):
    """
    Changing a strength must create a new line and retire the old one, never
    mutate the old row in place.

    Mutating it would retroactively relabel every dose already recorded against
    it: a week of 500mg doses would start claiming to have been 850mg. That is a
    quieter falsification than deleting the rows, and adherence analysis has no
    way to detect it.
    """
    presc_id, _, clinician_h = await _setup_verified_prescription(client, session)
    events_before = await _record_history(session, presc_id)

    rows = await session.execute(
        select(PrescribedMedication).where(
            PrescribedMedication.prescription_id == presc_id,
            PrescribedMedication.medicine_name == "Metformin",
        )
    )
    old = rows.scalars().one()
    old_id, old_strength = old.id, old.strength
    assert old_strength == "500mg"

    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json={
            "verified": True,
            "corrections": [
                {"medicine_name": "Metformin", "strength": "850mg", "frequency": "twice daily"},
                {"medicine_name": "Aspirin", "strength": "75mg", "frequency": "once daily"},
            ],
        },
        headers=clinician_h,
    )
    assert r.status_code == 200, r.text
    expire(session)
    recon = r.json()["reconciliation"]
    assert recon["added"] == 1, recon
    assert recon["discontinued"] == 1, recon

    # History survives the strength change.
    assert await _count(session, MedicationEvent) == events_before

    rows = await session.execute(
        select(PrescribedMedication).where(
            PrescribedMedication.prescription_id == presc_id,
            PrescribedMedication.medicine_name.ilike("metformin"),
        )
    )
    metformin = {m.strength: m for m in rows.scalars().all()}
    assert set(metformin) == {"500mg", "850mg"}, (
        "the superseded strength was not retained alongside the new one"
    )
    assert metformin["500mg"].id == old_id, "the old line was replaced rather than retired"
    assert metformin["500mg"].is_active is False
    assert metformin["850mg"].is_active is True


async def test_reactivating_a_discontinued_line_reuses_its_row(client, session):
    """
    Re-adding a medication the patient was previously taken off must reactivate
    the original row, reconnecting it to its own recorded doses, rather than
    starting a second row with no history.
    """
    presc_id, _, clinician_h = await _setup_verified_prescription(client, session)
    await _record_history(session, presc_id)

    keep_only_metformin = {
        "verified": True,
        "corrections": [
            {"medicine_name": "Metformin", "strength": "500mg", "frequency": "twice daily"}
        ],
    }
    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json=keep_only_metformin,
        headers=clinician_h,
    )
    assert r.status_code == 200, r.text
    expire(session)

    rows = await session.execute(
        select(PrescribedMedication).where(
            PrescribedMedication.prescription_id == presc_id,
            PrescribedMedication.medicine_name == "Aspirin",
        )
    )
    aspirin_id = rows.scalars().one().id

    # Clinician restarts the aspirin.
    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json={
            "verified": True,
            "corrections": [
                {"medicine_name": "Metformin", "strength": "500mg", "frequency": "twice daily"},
                {"medicine_name": "Aspirin", "strength": "75mg", "frequency": "once daily"},
            ],
        },
        headers=clinician_h,
    )
    assert r.status_code == 200, r.text
    expire(session)
    recon = r.json()["reconciliation"]
    assert recon["reactivated"] == 1, recon
    assert recon["added"] == 0, recon

    rows = await session.execute(
        select(PrescribedMedication).where(
            PrescribedMedication.prescription_id == presc_id,
            PrescribedMedication.medicine_name == "Aspirin",
        )
    )
    aspirin = rows.scalars().all()
    assert len(aspirin) == 1, "restarting the medication created a second row"
    assert aspirin[0].id == aspirin_id
    assert aspirin[0].is_active is True


async def test_duplicate_correction_lines_are_rejected(client, session):
    """
    Two indistinguishable entries in one payload are a client bug. Silently
    deduplicating them would hide it; the clinician should be told.
    """
    presc_id, _, clinician_h = await _setup_verified_prescription(client, session)

    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json={
            "verified": True,
            "corrections": [
                {"medicine_name": "Metformin", "strength": "500mg", "frequency": "twice daily"},
                {"medicine_name": "metformin", "strength": "500mg", "frequency": "Twice Daily"},
            ],
        },
        headers=clinician_h,
    )
    assert r.status_code == 422, r.text
    assert "more than once" in r.text


async def test_discontinued_medication_is_visible_to_clients(client, session):
    """
    is_active must be exposed. A client that cannot see it would render a
    discontinued drug as if the patient were still meant to take it.
    """
    presc_id, patient_h, clinician_h = await _setup_verified_prescription(client, session)

    r = await client.put(
        f"/api/v1/prescriptions/{presc_id}/verify",
        json={
            "verified": True,
            "corrections": [
                {"medicine_name": "Metformin", "strength": "500mg", "frequency": "twice daily"}
            ],
        },
        headers=clinician_h,
    )
    assert r.status_code == 200, r.text
    expire(session)

    r = await client.get(f"/api/v1/prescriptions/{presc_id}", headers=patient_h)
    assert r.status_code == 200, r.text
    expire(session)
    by_name = {m["medicine_name"]: m for m in r.json()["medications"]}
    assert "is_active" in by_name["Metformin"], "is_active is not exposed by the API"
    assert by_name["Metformin"]["is_active"] is True
    assert by_name["Aspirin"]["is_active"] is False
