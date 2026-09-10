"""
Tests for the patient's today-schedule: ``schedule_service.get_todays_doses`` and
``GET /api/v1/schedule/today``.

This endpoint exists to make dose logging reachable. ``POST /adherence/log`` requires
a ``schedule_id`` and nothing returned one, so the whole adherence write path was
unreachable from a client. That makes one test here the important one:
``test_schedule_id_round_trips_to_the_same_event_row``. If the instant this endpoint
reports and the instant ``record_patient_response`` derives ever disagree, the patient
taps "taken" on a dose displayed at 08:00, an event is written for a slot that was
never shown, and the displayed slot later expires MISSED — the adherence rate falls
for a dose that was actually taken. Both sides go through ``dose_instant_utc`` for
exactly that reason, and this asserts they still do.

Service-level tests pass ``reference_time`` rather than patching the clock. The
HTTP-level tests use the real clock, since the endpoint reads ``utcnow`` itself.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.medication_event import MedicationEvent, MedicationEventStatus, SkipReasonCode
from app.models.medication_schedule import MedicationSchedule, ScheduleLifecycle
from app.models.patient import Patient
from app.models.prescribed_medication import PrescribedMedication
from app.models.prescription import Prescription
from app.models.reminder import Reminder, ReminderStatus
from app.models.user import User
from app.services import schedule_service

from conftest import register

KARACHI = "Asia/Karachi"
NEW_YORK = "America/New_York"

# 2026-03-06 12:00Z is 17:00 in Karachi and 07:00 in New York, so "today" is the 6th
# in both — a reference time that does not itself straddle a date boundary.
NOON_UTC = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)

# US spring-forward 2026 is Sunday 8 March. The 10th is EDT, the 6th is EST.
AFTER_DST = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)


async def _patient(session, tz_name=KARACHI, email="today@example.com"):
    user = User(
        name="Today Patient",
        email=email,
        # bcrypt is slow and nothing here logs in through this user.
        hashed_password="not-a-real-hash",
        role="PATIENT",
    )
    user.patient = Patient(timezone=tz_name)
    session.add(user)
    await session.flush()
    return user.patient


async def _medication(
    session,
    patient,
    *,
    name="Metformin",
    strength="500 mg",
    dose="1 tablet",
    instructions="Take after food",
    is_active=True,
):
    presc = Prescription(
        patient_id=patient.id,
        prescription_date=date(2026, 3, 1),
        verification_status="VERIFIED",
    )
    session.add(presc)
    await session.flush()

    med = PrescribedMedication(
        prescription_id=presc.id,
        patient_id=patient.id,
        medicine_name=name,
        strength=strength,
        dose=dose,
        frequency="twice daily",
        instructions=instructions,
        is_active=is_active,
    )
    session.add(med)
    await session.flush()
    return med


async def _schedule(
    session,
    patient,
    med,
    dose_time,
    *,
    start=date(2026, 3, 1),
    end=None,
    status=ScheduleLifecycle.ACTIVE,
    relation_to_meal="AFTER_MEAL",
):
    sched = MedicationSchedule(
        prescribed_medication_id=med.id,
        patient_id=patient.id,
        scheduled_time=dose_time,
        relation_to_meal=relation_to_meal,
        start_date=start,
        end_date=end,
        status=status.value,
    )
    session.add(sched)
    await session.flush()
    return sched


async def test_unlogged_doses_are_pending_and_chronological(session):
    """
    Two dose times produce two doses, earliest first, both PENDING.

    PENDING is a derived value, not a stored one: no MedicationEvent row exists until
    something happens to a dose. A client must be able to tell "not yet logged" from
    "no data", so the absence of a row has to come back as an explicit status.
    """
    patient = await _patient(session)
    med = await _medication(session, patient)
    evening = await _schedule(session, patient, med, time(20, 0))
    morning = await _schedule(session, patient, med, time(8, 0))
    await session.commit()

    doses = await schedule_service.get_todays_doses(
        session, patient.id, reference_time=NOON_UTC
    )

    assert [d.schedule_id for d in doses] == [morning.id, evening.id]
    assert [d.scheduled_local_time for d in doses] == ["08:00", "20:00"]
    assert all(d.status == MedicationEventStatus.PENDING.value for d in doses)
    assert all(d.event_id is None for d in doses)
    assert all(d.reminder_id is None for d in doses)

    # Prescription detail travels with the dose so the UI needs one request.
    assert doses[0].medicine_name == "Metformin"
    assert doses[0].strength == "500 mg"
    assert doses[0].dose == "1 tablet"
    assert doses[0].relation_to_meal == "AFTER_MEAL"


async def test_scheduled_at_is_the_patient_local_instant_not_the_server_day(session):
    """
    08:00 local means 08:00 in the patient's zone, resolved per date.

    Karachi is a flat +05:00, so 08:00 local is 03:00Z. New York is not, which is why
    the same schedule is asserted either side of spring-forward: the local wall clock
    holds at 08:00 and the UTC instant moves.
    """
    karachi = await _patient(session, KARACHI, "karachi@example.com")
    k_med = await _medication(session, karachi)
    await _schedule(session, karachi, k_med, time(8, 0))

    ny = await _patient(session, NEW_YORK, "ny@example.com")
    n_med = await _medication(session, ny)
    await _schedule(session, ny, n_med, time(8, 0))
    await session.commit()

    k_doses = await schedule_service.get_todays_doses(
        session, karachi.id, reference_time=NOON_UTC
    )
    assert k_doses[0].scheduled_at == datetime(2026, 3, 6, 3, 0, tzinfo=timezone.utc)

    est = await schedule_service.get_todays_doses(
        session, ny.id, reference_time=NOON_UTC
    )
    edt = await schedule_service.get_todays_doses(
        session, ny.id, reference_time=AFTER_DST
    )

    assert est[0].scheduled_at == datetime(2026, 3, 6, 13, 0, tzinfo=timezone.utc)
    assert edt[0].scheduled_at == datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)

    tz = ZoneInfo(NEW_YORK)
    assert est[0].scheduled_at.astimezone(tz).time() == time(8, 0)
    assert edt[0].scheduled_at.astimezone(tz).time() == time(8, 0), (
        "the dose drifted off 08:00 local across the DST change"
    )
    assert est[0].scheduled_local_time == edt[0].scheduled_local_time == "08:00"


async def test_a_discontinued_medication_has_no_doses_today(session):
    """
    A medication marked inactive disappears from the list.

    This has to agree with ``create_due_reminders``, which filters on the same two
    flags. If the endpoint were more permissive the patient would see a dose that no
    reminder will ever fire for and that they have been taken off.
    """
    patient = await _patient(session)
    live = await _medication(session, patient, name="Metformin")
    stopped = await _medication(
        session, patient, name="Amlodipine", is_active=False
    )
    await _schedule(session, patient, live, time(8, 0))
    await _schedule(session, patient, stopped, time(9, 0))
    await session.commit()

    doses = await schedule_service.get_todays_doses(
        session, patient.id, reference_time=NOON_UTC
    )

    assert [d.medicine_name for d in doses] == ["Metformin"]


async def test_an_inactive_schedule_has_no_doses_today(session):
    """A superseded schedule row is retained for history but not shown."""
    patient = await _patient(session)
    med = await _medication(session, patient)
    await _schedule(session, patient, med, time(8, 0), status=ScheduleLifecycle.ACTIVE)
    await _schedule(
        session, patient, med, time(9, 0), status=ScheduleLifecycle.SUPERSEDED
    )
    await session.commit()

    doses = await schedule_service.get_todays_doses(
        session, patient.id, reference_time=NOON_UTC
    )

    assert [d.scheduled_local_time for d in doses] == ["08:00"]


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (date(2026, 3, 1), None, True),          # ongoing
        (date(2026, 3, 6), date(2026, 3, 6), True),   # single-day course, today
        (date(2026, 3, 7), None, False),         # starts tomorrow
        (date(2026, 3, 1), date(2026, 3, 5), False),  # finished yesterday
    ],
)
async def test_course_dates_bound_the_list(session, start, end, expected):
    """
    The course window is inclusive at both ends and evaluated against the patient's
    local today, matching ``create_due_reminders``.

    A course that finished yesterday must not still be prompting for doses, and one
    that starts tomorrow must not start a day early.
    """
    patient = await _patient(session)
    med = await _medication(session, patient)
    await _schedule(session, patient, med, time(8, 0), start=start, end=end)
    await session.commit()

    doses = await schedule_service.get_todays_doses(
        session, patient.id, reference_time=NOON_UTC
    )

    assert bool(doses) is expected


async def test_is_due_tracks_the_scheduled_instant(session):
    """
    ``is_due`` is false for a dose still in the future.

    The client needs this to decide what is actionable now. Offering "did you take
    it?" for a 20:00 dose at lunchtime invites a false confirmation.
    """
    patient = await _patient(session)
    med = await _medication(session, patient)
    await _schedule(session, patient, med, time(8, 0))    # 03:00Z — past at noon
    await _schedule(session, patient, med, time(20, 0))   # 15:00Z — future at noon
    await session.commit()

    doses = await schedule_service.get_todays_doses(
        session, patient.id, reference_time=NOON_UTC
    )

    assert [d.is_due for d in doses] == [True, False]


async def test_a_logged_dose_carries_its_event_status_and_reasons(session):
    """
    An existing event supplies status, confirmation time and both reason fields.

    The two reason fields are not interchangeable and the schema says so: the code is
    a trusted closed vocabulary, the free text is untrusted patient input. Both reach
    the client because the clinician should see what the patient actually wrote, but
    they are carried separately so the UI can render one as a value and the other as
    an attributed quotation.
    """
    patient = await _patient(session)
    med = await _medication(session, patient)
    sched = await _schedule(session, patient, med, time(8, 0))
    instant = schedule_service.dose_instant_utc(
        time(8, 0), date(2026, 3, 6), ZoneInfo(KARACHI)
    )

    reminder = Reminder(
        schedule_id=sched.id,
        patient_id=patient.id,
        scheduled_for=instant,
        status=ReminderStatus.SENT.value,
        channel="PUSH",
    )
    session.add(reminder)
    await session.flush()

    event = MedicationEvent(
        schedule_id=sched.id,
        patient_id=patient.id,
        reminder_id=reminder.id,
        scheduled_at=instant,
        status=MedicationEventStatus.SKIPPED.value,
        confirmed_at=instant + timedelta(minutes=5),
        recorded_by="PATIENT",
        skip_reason_code=SkipReasonCode.SIDE_EFFECTS.value,
        skip_reason="felt sick after the last one",
    )
    session.add(event)
    await session.commit()

    doses = await schedule_service.get_todays_doses(
        session, patient.id, reference_time=NOON_UTC
    )

    assert len(doses) == 1
    dose = doses[0]
    assert dose.status == MedicationEventStatus.SKIPPED.value
    assert dose.event_id == event.id
    assert dose.reminder_id == reminder.id
    assert dose.confirmed_at == instant + timedelta(minutes=5)
    assert dose.skip_reason_code == SkipReasonCode.SIDE_EFFECTS.value
    assert dose.skip_reason == "felt sick after the last one"


async def test_an_event_from_another_day_does_not_leak_into_today(session):
    """
    Yesterday's TAKEN event must not mark today's dose taken.

    The lookup is keyed on (schedule_id, instant), and a daily schedule reuses one
    schedule_id for every day of the course. Matching on schedule_id alone would show
    today's dose as already taken and suppress the prompt entirely.
    """
    patient = await _patient(session)
    med = await _medication(session, patient)
    sched = await _schedule(session, patient, med, time(8, 0))

    yesterday = schedule_service.dose_instant_utc(
        time(8, 0), date(2026, 3, 5), ZoneInfo(KARACHI)
    )
    session.add(
        MedicationEvent(
            schedule_id=sched.id,
            patient_id=patient.id,
            scheduled_at=yesterday,
            status=MedicationEventStatus.TAKEN.value,
            confirmed_at=yesterday,
            recorded_by="PATIENT",
        )
    )
    await session.commit()

    doses = await schedule_service.get_todays_doses(
        session, patient.id, reference_time=NOON_UTC
    )

    assert doses[0].status == MedicationEventStatus.PENDING.value
    assert doses[0].event_id is None


async def test_another_patients_schedule_is_not_returned(session):
    """Doses are scoped to the patient, not merely filtered client-side."""
    mine = await _patient(session, KARACHI, "mine@example.com")
    theirs = await _patient(session, KARACHI, "theirs@example.com")
    my_med = await _medication(session, mine, name="Metformin")
    their_med = await _medication(session, theirs, name="Warfarin")
    await _schedule(session, mine, my_med, time(8, 0))
    await _schedule(session, theirs, their_med, time(8, 0))
    await session.commit()

    doses = await schedule_service.get_todays_doses(
        session, mine.id, reference_time=NOON_UTC
    )

    assert [d.medicine_name for d in doses] == ["Metformin"]


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


async def test_today_schedule_requires_authentication(client):
    r = await client.get("/api/v1/schedule/today")
    assert r.status_code in (401, 403), r.text


async def test_a_clinician_has_no_patient_schedule(client):
    """
    A clinician account is not a patient and gets a clear 400, not an empty list.

    The role value and the skip-reason value now agree: CLINICIAN and
    CLINICIAN_INSTRUCTED. This used to read DOCTOR here and note the inconsistency;
    migration ``9f2c1d7ab4e0`` resolved it.
    """
    headers = await register(client, "doc-today@example.com", role="CLINICIAN")

    r = await client.get("/api/v1/schedule/today", headers=headers)

    assert r.status_code == 400, r.text
    assert "not a patient" in r.json()["detail"].lower()


async def test_endpoint_reports_totals_and_an_empty_list_when_nothing_is_scheduled(
    client,
):
    """
    A patient with no prescriptions gets an empty list, not a 404.

    Zero doses today is a normal state, and the client's dashboard has to distinguish
    it from an error.
    """
    headers = await register(client, "empty-today@example.com")

    r = await client.get("/api/v1/schedule/today", headers=headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["doses"] == []
    assert body["total_doses"] == 0
    assert body["doses_taken"] == 0
    assert body["doses_remaining"] == 0
    assert body["local_date"] == datetime.now(timezone.utc).date().isoformat()
    assert body["timezone"]


async def test_schedule_id_round_trips_to_the_same_event_row(client, session):
    """
    The instant this endpoint reports is the instant the write path derives.

    This is the reason the endpoint exists and the reason ``dose_instant_utc`` is a
    single shared function. The client is given a ``schedule_id`` and nothing else
    about timing; it posts that back; the backend re-derives the instant. If the two
    derivations disagreed, ``MedicationEvent.scheduled_at`` would not equal the
    ``scheduled_at`` that was displayed, and the dose the patient confirmed would
    still be sitting there waiting to expire MISSED.

    Uses the real clock on both sides, which is the point — a frozen clock could hide
    a disagreement between two code paths that each read the time themselves.
    """
    headers = await register(client, "roundtrip@example.com")
    patient = (
        await session.execute(
            select(Patient).join(User).where(User.email == "roundtrip@example.com")
        )
    ).scalars().one()

    med = await _medication(session, patient, name="Metformin")
    # Yesterday onwards, so the course is open regardless of the local date, and a
    # dose time already past so it is actionable now.
    local_today = datetime.now(timezone.utc).astimezone(
        schedule_service.resolve_patient_timezone(patient)
    ).date()
    await _schedule(
        session, patient, med, time(0, 30), start=local_today - timedelta(days=1)
    )
    await session.commit()

    before = await client.get("/api/v1/schedule/today", headers=headers)
    assert before.status_code == 200, before.text
    doses = before.json()["doses"]
    assert len(doses) == 1, doses
    dose = doses[0]
    assert dose["status"] == "PENDING"
    assert dose["is_due"] is True

    logged = await client.post(
        "/api/v1/adherence/log",
        headers=headers,
        json={"schedule_id": dose["schedule_id"], "status": "TAKEN"},
    )
    assert logged.status_code == 201, logged.text

    written = (
        await session.execute(
            select(MedicationEvent).where(
                MedicationEvent.schedule_id == dose["schedule_id"]
            )
        )
    ).scalars().all()
    assert len(written) == 1, (
        f"expected exactly one event for the displayed dose, got {len(written)}: "
        f"{[(e.id, e.scheduled_at.isoformat(), e.status) for e in written]}"
    )
    assert written[0].scheduled_at == datetime.fromisoformat(dose["scheduled_at"]), (
        "the event was written for a different instant than the one displayed"
    )

    after = await client.get("/api/v1/schedule/today", headers=headers)
    body = after.json()
    assert body["doses"][0]["status"] == "TAKEN"
    assert body["doses"][0]["event_id"] == written[0].id
    assert body["doses_taken"] == 1
    assert body["doses_remaining"] == 0
    assert body["total_doses"] == 1


async def test_a_structured_skip_reason_round_trips_through_the_schedule(
    client, session
):
    """
    The skip-reason code the UI collects comes back on the dose.

    The dose-logging screen offers a closed list precisely so the barrier classifier
    does not have to guess from prose. That only helps if the value survives the
    round trip and is readable back — otherwise the UI cannot show the patient what
    they already told it.
    """
    headers = await register(client, "skipcode@example.com")
    patient = (
        await session.execute(
            select(Patient).join(User).where(User.email == "skipcode@example.com")
        )
    ).scalars().one()

    med = await _medication(session, patient, name="Amlodipine")
    local_today = datetime.now(timezone.utc).astimezone(
        schedule_service.resolve_patient_timezone(patient)
    ).date()
    await _schedule(
        session, patient, med, time(0, 30), start=local_today - timedelta(days=1)
    )
    await session.commit()

    dose = (await client.get("/api/v1/schedule/today", headers=headers)).json()["doses"][0]

    logged = await client.post(
        "/api/v1/adherence/log",
        headers=headers,
        json={
            "schedule_id": dose["schedule_id"],
            "status": "SKIPPED",
            "skip_reason_code": SkipReasonCode.CLINICIAN_INSTRUCTED.value,
            "skip_reason": "cardiologist told me to hold it this week",
        },
    )
    assert logged.status_code == 201, logged.text

    after = (await client.get("/api/v1/schedule/today", headers=headers)).json()
    dose = after["doses"][0]
    assert dose["status"] == "SKIPPED"
    assert dose["skip_reason_code"] == SkipReasonCode.CLINICIAN_INSTRUCTED.value
    assert dose["skip_reason"] == "cardiologist told me to hold it this week"
    # A skipped dose is resolved, so it is neither taken nor still outstanding.
    assert after["doses_taken"] == 0
    assert after["doses_remaining"] == 0
