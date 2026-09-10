"""
End-to-end vertical slice: missed doses -> escalation -> safety-preserving review.

Converted from ``run_e2e_suite()``, a single 130-line chain that pytest never ran.
Beyond not being collected, the original had the same two defects as the other
scripts: it drove ``AsyncSessionLocal`` against ``medication.db``, and it opened by
*deleting every event, schedule, medication and prescription* for its patient in
order to be re-runnable. It also had to tolerate its own leftovers — registration
accepted 201 *or* 400 ("already registered"), which means the run after the first
was no longer testing registration at all.

Splitting the chain into separate tests matters here more than elsewhere: as one
function, a guardrail regression and an adherence-arithmetic regression produced the
same opaque failure, and whichever assertion came first hid the rest.

Note on what this layer is: ``AdherenceAnalysisService`` is deterministic — it composes
its explanation and clinical brief from the safety assessment and the adherence
metrics, with no model call. So the guardrail tests below pin the *validators and
the composition*, which is genuinely what they exist to protect. They do not yet
demonstrate that the guardrails can catch a generative model saying something
dangerous, because nothing generative is wired in.
"""

from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    MedicationEvent,
    MedicationSchedule,
    Patient,
    PrescribedMedication,
    Prescription,
    ScheduleLifecycle,
    User,
)

BASE = "/api/v1"

EMAIL = "e2e_vertical_slice_01@example.com"
PASSWORD = "E2ETestPass123!"

KNOWN_CITATION_SOURCES = ("DOC-FDA", "AHA", "DailyMed", "NICE", "ESC")


async def _login(client, email=EMAIL, password=PASSWORD):
    resp = await client.post(
        f"{BASE}/auth/login", data={"username": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def slice_patient(client, session):
    """
    A registered asthmatic patient prescribed propranolol, with three consecutive
    missed doses.

    The conflict is deliberate and clinically real: propranolol is a non-selective
    beta blocker and is contraindicated in asthma. Combined with the missed doses
    this is the scenario the whole chain exists to surface.

    Registration goes through HTTP so the real auth path is exercised; the
    prescription data is inserted directly, which is only about speed — the
    endpoints that create it are covered elsewhere.
    """
    resp = await client.post(
        f"{BASE}/auth/register",
        json={
            "name": "E2E Slice Patient",
            "email": EMAIL,
            "password": PASSWORD,
            "role": "PATIENT",
        },
    )
    # Unconditional 201: the database is per-test, so a duplicate here would mean a
    # real bug rather than a leftover from a previous run.
    assert resp.status_code == 201, resp.text

    user = (
        await session.execute(select(User).where(User.email == EMAIL))
    ).scalars().first()
    assert user is not None, "registration returned 201 but no user row exists"
    patient = (
        await session.execute(select(Patient).where(Patient.user_id == user.id))
    ).scalars().first()
    assert patient is not None, (
        "registration returned 201 but no patient profile exists -- this is the "
        "atomicity failure covered by test_registration_atomicity.py"
    )

    patient.chronic_conditions = ["Asthma"]
    patient.allergies = ["Penicillin"]

    presc = Prescription(
        patient_id=patient.id,
        doctor_name="Dr. E2E",
        clinic_name="Integration Test Clinic",
        prescription_date=date.today(),
        verification_status="VERIFIED",
    )
    session.add(presc)
    await session.flush()

    med = PrescribedMedication(
        prescription_id=presc.id,
        patient_id=patient.id,
        medicine_name="Inderal 40mg",  # propranolol
        frequency="twice daily",
        is_active=True,
    )
    session.add(med)
    await session.flush()

    schedule = MedicationSchedule(
        prescribed_medication_id=med.id,
        patient_id=patient.id,
        scheduled_time=time(9, 0),
        start_date=date.today() - timedelta(days=7),
        status=ScheduleLifecycle.ACTIVE.value,
    )
    session.add(schedule)
    await session.flush()

    for days_ago in (1, 2, 3):
        session.add(
            MedicationEvent(
                schedule_id=schedule.id,
                patient_id=patient.id,
                scheduled_at=datetime.combine(
                    date.today() - timedelta(days=days_ago),
                    time(9, 0),
                    tzinfo=timezone.utc,
                ),
                status="MISSED",
                recorded_by="SYSTEM",
            )
        )

    # Committed before any request: the endpoints read through their own sessions
    # and cannot see uncommitted state from this one.
    await session.commit()

    return {"patient_id": patient.id, "headers": await _login(client)}


async def test_me_returns_the_registered_identity(client, slice_patient):
    """The JWT resolves to the user who logged in, over the real auth dependency."""
    resp = await client.get(f"{BASE}/auth/me", headers=slice_patient["headers"])

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == EMAIL
    assert body["role"] == "PATIENT"


async def test_missed_doses_lower_adherence_and_trigger_escalation(
    client, slice_patient
):
    """
    Three consecutive misses show up in the score and set the escalation flag.

    This is the arithmetic the clinical brief and the safety bridge both consume, so
    it is asserted at the HTTP boundary — serialization included — rather than only
    at the service layer.
    """
    resp = await client.get(
        f"{BASE}/adherence/score?period=7d", headers=slice_patient["headers"]
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["adherence_rate"] < 80.0, (
        f"three missed doses produced a rate of {body['adherence_rate']}%"
    )
    assert body["should_escalate"] is True, (
        f"no escalation for three consecutive misses; reasons: "
        f"{body['escalation_reasons']}"
    )
    assert body["escalation_reasons"], "escalating with no stated reason"


async def test_analysis_preserves_the_deterministic_safety_verdict(
    client, slice_patient
):
    """
    The analysis layer reports CRITICAL and keeps the human-review flag.

    This is the invariant the whole design rests on: the rules engine decides, the
    analysis layer explains. If it could soften propranolol-in-asthma to something
    milder on its way to being phrased for a patient, every guardrail behind it is
    decorative.
    """
    resp = await client.get(
        f"{BASE}/adherence/analysis?period=7d", headers=slice_patient["headers"]
    )
    print("\n--- analysis endpoint ---")
    print(f"status_code: {resp.status_code}")
    assert resp.status_code == 200, resp.text
    review = resp.json()
    
    print("\n--- clinical_brief.insights ---")
    import json
    print(json.dumps(review.get("clinical_brief", {}).get("insights", {}), indent=2))

    assert review["safety_risk_level"] == "CRITICAL", (
        f"propranolol + asthma came back as {review['safety_risk_level']!r}"
    )
    assert review["requires_human_review"] is True
    assert review["validation_passed"] is True, (
        "the layer's own output validation rejected its response"
    )


async def test_analysis_never_advises_stopping_or_doubling_a_dose(
    client, slice_patient
):
    """
    The patient-facing text contains no dangerous self-management instruction.

    Telling a patient to stop a beta blocker abruptly, or to double up on a missed
    dose, is direct physical harm. Note the honest limit of this test: the text is
    currently template-composed, so it passes by construction. It is kept as a
    standing tripwire for the point at which generated text starts flowing through
    this field.
    """
    resp = await client.get(
        f"{BASE}/adherence/analysis?period=7d", headers=slice_patient["headers"]
    )
    assert resp.status_code == 200, resp.text
    explanation = resp.json()["patient_explanation"]

    assert explanation["summary"], "the patient was given an empty summary"

    advice = explanation["what_to_do_next"].lower()
    for forbidden in ("stop taking", "double your", "take a double dose"):
        assert forbidden not in advice, (
            f"unsafe self-management instruction {forbidden!r} in patient advice: "
            f"{explanation['what_to_do_next']}"
        )


async def test_analysis_insights_produced(client, slice_patient):
    """
    The analysis endpoint produces structured clinical brief insights.
    """
    resp = await client.get(
        f"{BASE}/adherence/analysis?period=7d", headers=slice_patient["headers"]
    )
    assert resp.status_code == 200, resp.text
    brief = resp.json()["clinical_brief"]

    assert brief["insights"] is not None
    assert "trend" in brief["insights"]
    assert isinstance(brief["insights"]["concerning_patterns"], list)
    assert isinstance(brief["insights"]["possible_barriers"], list)

    assert brief["patient_id"] == slice_patient["patient_id"]
    assert brief["adherence_rate"] < 80.0, brief["adherence_rate"]


async def test_one_patients_adherence_is_not_visible_to_another(client, slice_patient):
    """
    Tenancy. A second patient's review reflects their own empty history, not the
    seeded patient's misses.

    The original script never checked this, yet it is the most consequential
    invariant in a system holding more than one person's medication record: every
    adherence and safety endpoint resolves the patient from the JWT, and a single
    query that filtered on the wrong id would show one patient another's clinical
    data while still returning a confident 200.
    """
    other_email = "e2e_other_patient@example.com"
    resp = await client.post(
        f"{BASE}/auth/register",
        json={
            "name": "Unrelated Patient",
            "email": other_email,
            "password": PASSWORD,
            "role": "PATIENT",
        },
    )
    assert resp.status_code == 201, resp.text
    other_headers = await _login(client, other_email)

    score = await client.get(f"{BASE}/adherence/score?period=7d", headers=other_headers)
    assert score.status_code == 200, score.text
    body = score.json()

    assert body["total_missed"] == 0, (
        "a patient with no medication history was shown missed doses "
        f"({body['total_missed']}), which can only have come from another patient"
    )
    assert body["expected_doses"] == 0, body["expected_doses"]
    assert body["should_escalate"] is False, body["escalation_reasons"]
