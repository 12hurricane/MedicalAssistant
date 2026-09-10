"""
Tests for the medication-schedule lifecycle and the deletion protection around it.

Two changes are under test here, and they exist as one pair:

1. ``MedicationSchedule.status`` replaced a boolean ``active``. The boolean could not
   distinguish "the clinician discontinued this medication" (CANCELLED) from "a newer
   schedule replaced this row" (SUPERSEDED), and it reported a finished course as still
   active forever, because both consumers re-filtered on the course dates at query time.

2. ``medication_events.schedule_id`` became ON DELETE RESTRICT. This is what turns
   "regeneration retires rows instead of deleting them" from an intention in a docstring
   into something the database enforces.

Point 2 is the one worth being explicit about, because the failure it prevents was
silent. Before this, ``DELETE FROM medication_schedules WHERE id = 36`` against the
development database removed eight logged doses and returned success. There was no code
path that did it *today* -- the ``prescription.medications.clear()`` that used to fire
``delete-orphan`` on collection mutation is gone -- but that is a statement about the
current call sites, not about the schema. The next person to add a cleanup routine, an
admin delete endpoint, or a "remove this medication" button would have inherited a
schema where the destructive version is the one that runs without complaint.

``conftest.engine`` enables ``PRAGMA foreign_keys=ON``. Without it every RESTRICT
assertion in this file would pass for entirely the wrong reason: SQLite would ignore the
constraint, the delete would succeed, and the test would be asserting nothing.
"""

from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models.medication_event import MedicationEvent, MedicationEventStatus
from app.models.medication_schedule import (
    STORED_SCHEDULE_STATUSES,
    MedicationSchedule,
    ScheduleLifecycle,
)
from app.models.patient import Patient
from app.models.prescribed_medication import PrescribedMedication
from app.models.prescription import Prescription
from app.models.user import User
from app.services import schedule_service

START = date(2026, 3, 1)


async def _patient(session, email="lifecycle@example.com"):
    user = User(
        name="Lifecycle Patient",
        email=email,
        hashed_password="not-a-real-hash",
        role="PATIENT",
    )
    user.patient = Patient(timezone="Asia/Karachi")
    session.add(user)
    await session.flush()
    return user.patient


async def _prescription(session, patient):
    presc = Prescription(
        patient_id=patient.id,
        prescription_date=START,
        verification_status="VERIFIED",
    )
    session.add(presc)
    await session.flush()
    return presc


async def _medication(
    session, patient, presc, *, name="Metformin", frequency="twice daily", is_active=True
):
    med = PrescribedMedication(
        prescription_id=presc.id,
        patient_id=patient.id,
        medicine_name=name,
        strength="500 mg",
        dose="1 tablet",
        frequency=frequency,
        is_active=is_active,
    )
    session.add(med)
    await session.flush()
    return med


async def _schedule(session, patient, med, dose_time=time(8, 0), *, end=None, status=None):
    sched = MedicationSchedule(
        prescribed_medication_id=med.id,
        patient_id=patient.id,
        scheduled_time=dose_time,
        start_date=START,
        end_date=end,
        status=(status or ScheduleLifecycle.ACTIVE).value,
    )
    session.add(sched)
    await session.flush()
    return sched


async def _logged_dose(session, sched, *, day=START, status=MedicationEventStatus.TAKEN):
    event = MedicationEvent(
        schedule_id=sched.id,
        patient_id=sched.patient_id,
        scheduled_at=datetime.combine(day, sched.scheduled_time, tzinfo=timezone.utc),
        status=status.value,
    )
    session.add(event)
    await session.flush()
    return event


async def _event_count(session) -> int:
    return (await session.execute(select(func.count()).select_from(MedicationEvent))).scalar_one()


# --------------------------------------------------------------------------------------
# Deletion protection
# --------------------------------------------------------------------------------------


async def test_deleting_a_schedule_with_logged_doses_is_refused(session):
    """
    The central guarantee: adherence history cannot be removed as a side effect.

    A schedule row is a plan. A medication_event is a record of what a patient actually
    did, it is derived from nothing, and it is the only input to the adherence score --
    so deleting one is unrecoverable and silently changes a clinical number. The FK is
    RESTRICT, so the database refuses rather than obliging.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    sched = await _schedule(session, patient, med)
    await _logged_dose(session, sched)
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.execute(
            text("DELETE FROM medication_schedules WHERE id = :sid"), {"sid": sched.id}
        )
        await session.commit()
    await session.rollback()

    assert await _event_count(session) == 1, "the logged dose was destroyed anyway"


async def test_orm_delete_of_a_schedule_is_refused_too(session):
    """
    ``db.delete(schedule)`` raises rather than cascading.

    Asserted separately from the raw DELETE above because SQLAlchemy could defeat the
    constraint on its own: with the previous ``cascade="all, delete-orphan"`` it would
    have issued the child DELETEs itself, in the right order, and the database would
    never have had the chance to object. ``passive_deletes="all"`` is what makes the ORM
    stand aside and let the schema decide.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    sched = await _schedule(session, patient, med)
    await _logged_dose(session, sched)
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.delete(sched)
        await session.flush()
    await session.rollback()

    assert await _event_count(session) == 1


async def test_removing_an_event_from_the_collection_cannot_destroy_it(session):
    """
    The exact shape of the historic bug, pinned.

    ``delete-orphan`` fires on *collection mutation*, not only on an explicit delete, so
    ``schedule.events.clear()`` was enough to erase a patient's history -- no
    ``db.delete`` anywhere in the diff, nothing that reads as dangerous at the call site.
    That is why the cascade is gone from the relationship rather than merely avoided by
    convention.

    It now raises, and the mechanism is worth naming because it is not the one the
    RESTRICT provides: de-associating a child makes SQLAlchemy try to NULL its
    ``schedule_id``, which is NOT NULL. (``passive_deletes="all"`` suppresses that
    nulling only for parent *deletes*.) So the outcome is an IntegrityError from a
    different constraint than the delete tests exercise -- what matters is that the
    write is refused and the row is still there afterwards.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    sched = await _schedule(session, patient, med)
    await _logged_dose(session, sched)
    await session.commit()

    loaded = (
        await session.execute(
            select(MedicationSchedule).where(MedicationSchedule.id == sched.id)
        )
    ).scalar_one()
    await session.refresh(loaded, ["events"])
    assert len(loaded.events) == 1

    loaded.events.clear()
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    assert await _event_count(session) == 1, (
        "clearing the collection deleted the history -- delete-orphan is back"
    )


async def test_deleting_a_prescribed_medication_with_history_is_refused(session):
    """
    Transitive protection, which is the reason one constraint was enough.

    ``prescribed_medications`` CASCADEs into ``medication_schedules``, so a delete here
    used to reach adherence history two levels down: on the development database,
    removing one prescribed medication took all fourteen schedules and all fifty-six
    events with it. The cascade now terminates on the RESTRICT, and the whole statement
    is rolled back.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    sched = await _schedule(session, patient, med)
    await _logged_dose(session, sched)
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.execute(
            text("DELETE FROM prescribed_medications WHERE id = :mid"), {"mid": med.id}
        )
        await session.commit()
    await session.rollback()

    assert await _event_count(session) == 1
    schedules = (await session.execute(select(func.count()).select_from(MedicationSchedule))).scalar_one()
    assert schedules == 1


async def test_deleting_the_patient_still_works(session):
    """
    Erasure is deliberately *not* foreclosed, and that asymmetry is the design.

    Every narrower delete is refused, but a patient-level delete succeeds: events carry
    their own ON DELETE CASCADE from ``patients``, so SQLite removes them by that route
    before the schedule FK can object. A hospital cannot be told its data-protection
    obligations are blocked by a foreign key, so "delete this person entirely" has to
    remain expressible while "tidy up these schedule rows" does not.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    sched = await _schedule(session, patient, med)
    await _logged_dose(session, sched)
    await session.commit()

    await session.execute(
        text("DELETE FROM patients WHERE id = :pid"), {"pid": patient.id}
    )
    await session.commit()

    assert await _event_count(session) == 0
    remaining = (await session.execute(select(func.count()).select_from(MedicationSchedule))).scalar_one()
    assert remaining == 0


async def test_a_schedule_with_no_history_can_still_be_deleted(session):
    """
    RESTRICT protects history, not schedule rows for their own sake.

    Worth stating, because a constraint that also blocked deleting a never-used row
    would make genuine mistakes -- a schedule created from a misread prescription and
    corrected a minute later -- permanently unfixable, and would push someone toward
    disabling the constraint rather than working with it.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    sched = await _schedule(session, patient, med)
    await session.commit()

    await session.delete(sched)
    await session.commit()

    remaining = (await session.execute(select(func.count()).select_from(MedicationSchedule))).scalar_one()
    assert remaining == 0


# --------------------------------------------------------------------------------------
# The stored vocabulary
# --------------------------------------------------------------------------------------


def test_completed_is_not_a_storable_status():
    """COMPLETED is derived; the stored set must not contain it."""
    assert ScheduleLifecycle.COMPLETED.value not in STORED_SCHEDULE_STATUSES
    assert STORED_SCHEDULE_STATUSES == {"ACTIVE", "CANCELLED", "SUPERSEDED"}


@pytest.mark.parametrize("bad", ["COMPLETED", "INACTIVE", "active", ""])
async def test_the_database_refuses_an_unstorable_status(session, bad):
    """
    The CHECK constraint, exercised through raw SQL so nothing in Python can be
    credited for the rejection.

    COMPLETED is the case that matters. It is a legitimate-looking value that a future
    contributor would reasonably write, and a stored COMPLETED reintroduces the precise
    defect ``status`` was created to remove: a cached calculation that goes stale. The
    row would stop dosing, and extending the course by moving ``end_date`` would no
    longer bring it back, because a stored status outranks the dates.

    ``"active"`` is in the list too -- the constraint is case-sensitive, and a
    lowercased value would otherwise slip through and match nothing.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    await session.commit()

    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "INSERT INTO medication_schedules "
                "(prescribed_medication_id, patient_id, scheduled_time, start_date, status) "
                "VALUES (:mid, :pid, '08:00:00', :start, :status)"
            ),
            {"mid": med.id, "pid": patient.id, "start": START.isoformat(), "status": bad},
        )
        await session.commit()
    await session.rollback()


async def test_the_database_refuses_an_update_to_an_unstorable_status(session):
    """The constraint applies to UPDATEs as well, including through the ORM."""
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    sched = await _schedule(session, patient, med)
    await session.commit()

    sched.status = ScheduleLifecycle.COMPLETED.value
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


# --------------------------------------------------------------------------------------
# Derived COMPLETED
# --------------------------------------------------------------------------------------


def _bare(status, end):
    """A schedule instance with no session -- ``lifecycle_on`` is pure."""
    return MedicationSchedule(
        prescribed_medication_id=1,
        patient_id=1,
        scheduled_time=time(8, 0),
        start_date=START,
        end_date=end,
        status=status.value,
    )


def test_an_open_ended_active_schedule_is_never_completed():
    """No end_date means an ongoing medication; it cannot run out."""
    sched = _bare(ScheduleLifecycle.ACTIVE, None)
    assert sched.lifecycle_on(date(2099, 1, 1)) is ScheduleLifecycle.ACTIVE


def test_completed_is_derived_from_the_end_date():
    sched = _bare(ScheduleLifecycle.ACTIVE, date(2026, 3, 10))
    assert sched.lifecycle_on(date(2026, 3, 9)) is ScheduleLifecycle.ACTIVE
    # Inclusive: the last day of a course is still a dosing day.
    assert sched.lifecycle_on(date(2026, 3, 10)) is ScheduleLifecycle.ACTIVE
    assert sched.lifecycle_on(date(2026, 3, 11)) is ScheduleLifecycle.COMPLETED


def test_extending_a_course_revives_the_schedule_with_no_second_write():
    """
    The argument for deriving rather than storing, as an assertion.

    Moving ``end_date`` forward is enough; nothing has to remember to flip a status
    back. Had COMPLETED been stored, this row would need two writes to resume and would
    stay silently dark if the second one were ever missed.
    """
    sched = _bare(ScheduleLifecycle.ACTIVE, date(2026, 3, 10))
    day = date(2026, 3, 15)
    assert sched.lifecycle_on(day) is ScheduleLifecycle.COMPLETED

    sched.end_date = date(2026, 3, 31)
    assert sched.lifecycle_on(day) is ScheduleLifecycle.ACTIVE


@pytest.mark.parametrize(
    "status", [ScheduleLifecycle.CANCELLED, ScheduleLifecycle.SUPERSEDED]
)
def test_a_retired_status_outranks_the_calendar(status):
    """
    A course stopped halfway through did not complete.

    Reporting COMPLETED for a cancelled course would be the worst available answer: it
    reads as "the patient finished their treatment" when the truth is that a clinician
    stopped it, and those lead a reviewer to opposite conclusions.
    """
    sched = _bare(status, date(2026, 3, 10))
    assert sched.lifecycle_on(date(2026, 3, 20)) is status
    assert sched.lifecycle_on(date(2026, 3, 1)) is status


def test_lifecycle_on_rejects_a_status_it_cannot_classify():
    """
    Loud rather than lenient.

    The CHECK constraint makes this unreachable through the database, so the only way
    here is an unsaved instance built in code. Defaulting to ACTIVE would let a typo
    dispatch reminders; raising surfaces it at the first read.
    """
    sched = _bare(ScheduleLifecycle.ACTIVE, None)
    sched.status = "PAUSED"
    with pytest.raises(ValueError):
        sched.lifecycle_on(date(2026, 3, 1))


# --------------------------------------------------------------------------------------
# Which reason regeneration records
# --------------------------------------------------------------------------------------


async def _generate(session, presc):
    await session.refresh(presc, ["medications"])
    return await schedule_service.generate_schedules(session, presc, START)


async def _statuses(session, med_id) -> dict[time, str]:
    rows = await session.execute(
        select(MedicationSchedule.scheduled_time, MedicationSchedule.status).where(
            MedicationSchedule.prescribed_medication_id == med_id
        )
    )
    return dict(rows.all())


async def test_a_dropped_dose_time_is_superseded_not_cancelled(session):
    """
    The medication is still prescribed, so the old row was *replaced*.

    This distinction is the whole point of the column. A clinician looking at the 20:00
    slot with no logged doses after the correction needs to know the plan changed, not
    that the patient stopped taking their medication -- SUPERSEDED says the former,
    CANCELLED would say the latter.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc, frequency="twice daily")
    await session.commit()

    first = await _generate(session, presc)
    assert first.created == 2
    await session.commit()

    med.frequency = "once daily"
    await session.flush()
    second = await _generate(session, presc)
    await session.commit()

    assert second.superseded == 1
    assert second.cancelled == 0
    assert await _statuses(session, med.id) == {
        time(8, 0): ScheduleLifecycle.ACTIVE.value,
        time(20, 0): ScheduleLifecycle.SUPERSEDED.value,
    }


async def test_a_discontinued_medication_has_its_schedules_cancelled(session):
    """
    The medication is gone, so the remaining doses were not meant to be taken.

    That is what makes CANCELLED clinically different from SUPERSEDED downstream: the
    absent doses are not non-adherence, and treating them as such would push a patient's
    score down for following instructions.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc, frequency="twice daily")
    await session.commit()

    await _generate(session, presc)
    await session.commit()

    med.is_active = False
    await session.flush()
    result = await _generate(session, presc)
    await session.commit()

    assert result.cancelled == 2
    assert result.superseded == 0
    assert set((await _statuses(session, med.id)).values()) == {
        ScheduleLifecycle.CANCELLED.value
    }


async def test_a_reinstated_medication_revives_its_own_rows(session):
    """
    Reviving beats inserting: the same course, slot and start date is the same schedule.

    A new row would leave the logged doses attached to a retired one and split a single
    course's history across two schedule ids -- and ``uq_schedule_med_time_start`` would
    reject the insert anyway.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc, frequency="once daily")
    await session.commit()

    await _generate(session, presc)
    await session.commit()
    original = (
        await session.execute(select(MedicationSchedule.id))
    ).scalar_one()

    med.is_active = False
    await session.flush()
    await _generate(session, presc)
    await session.commit()

    med.is_active = True
    await session.flush()
    result = await _generate(session, presc)
    await session.commit()

    assert result.reactivated == 1
    assert result.created == 0
    ids = (await session.execute(select(MedicationSchedule.id))).scalars().all()
    assert ids == [original], "the revived course was given a new schedule row"
    assert (await _statuses(session, med.id)) == {
        time(8, 0): ScheduleLifecycle.ACTIVE.value
    }


async def test_rejecting_a_prescription_cancels_its_schedules(session):
    """
    ``cancel_schedules`` is CANCELLED, never SUPERSEDED: nothing replaces these doses,
    the decision was that they should not be taken at all.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc, frequency="twice daily")
    await session.commit()

    await _generate(session, presc)
    await session.commit()

    await session.refresh(presc, ["medications"])
    count = await schedule_service.cancel_schedules(session, presc)
    await session.commit()

    assert count == 2
    assert set((await _statuses(session, med.id)).values()) == {
        ScheduleLifecycle.CANCELLED.value
    }


async def test_cancelling_twice_is_idempotent(session):
    """Only live rows are touched, so a repeated rejection reports zero."""
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    await _medication(session, patient, presc, frequency="once daily")
    await session.commit()

    await _generate(session, presc)
    await session.commit()
    await session.refresh(presc, ["medications"])

    assert await schedule_service.cancel_schedules(session, presc) == 1
    await session.commit()
    await session.refresh(presc, ["medications"])
    assert await schedule_service.cancel_schedules(session, presc) == 0


def test_deactivated_is_the_sum_of_the_two_reasons():
    """
    The published wire field is derived, so the counts cannot disagree with their total.

    ``ScheduleGenerationResponse.deactivated`` is in ``openapi.json`` and generated into
    the Flutter models, so the name stays put; splitting it would be a breaking contract
    change for a number no hand-written client code reads.
    """
    result = schedule_service.ScheduleGenerationResult(
        created=1, reactivated=2, cancelled=3, superseded=4, unchanged=5
    )
    assert result.deactivated == 7
    assert result.active_total == 8


# --------------------------------------------------------------------------------------
# The consumers agree with the derivation
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status", [ScheduleLifecycle.CANCELLED, ScheduleLifecycle.SUPERSEDED]
)
async def test_retired_schedules_produce_no_doses_today(session, status):
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    await _schedule(session, patient, med, time(8, 0), status=status)
    await session.commit()

    doses = await schedule_service.get_todays_doses(
        session, patient.id, reference_time=datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    )
    assert doses == []


async def test_a_completed_course_produces_no_doses_today(session):
    """
    The half of the filter that status cannot express.

    This row is stored ACTIVE and its course ended on the 5th, so only the date window
    excludes it -- which is exactly why COMPLETED is derived and why removing the date
    filter in favour of the status column would put finished courses back on the
    patient's list.
    """
    patient = await _patient(session)
    presc = await _prescription(session, patient)
    med = await _medication(session, patient, presc)
    sched = await _schedule(session, patient, med, time(8, 0), end=date(2026, 3, 5))
    await session.commit()

    reference = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    assert sched.status == ScheduleLifecycle.ACTIVE.value
    assert sched.lifecycle_on(date(2026, 3, 6)) is ScheduleLifecycle.COMPLETED
    assert await schedule_service.get_todays_doses(
        session, patient.id, reference_time=reference
    ) == []
