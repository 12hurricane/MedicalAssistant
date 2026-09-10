"""
No-data adherence semantics.

The contract: with no expected doses there is no adherence rate. Not 100%, not 0% —
null, meaning "not measurable from this window".

This used to report ``adherence_rate=100.0, missed_rate=0.0, skipped_rate=0.0``, which
is arithmetically defensible (zero of zero doses were missed) and clinically wrong. It
describes a patient with no medication history as perfectly adherent, and it is wrong
for exactly the patients a clinician knows least about: the newly enrolled ones. The
Flutter client happened to render an em dash, but a contract that only reads correctly
because one client is careful will eventually be read by a client that is not — the
clinician dashboard in Phase 5.5 among them.

So the tests below assert on the API payload and on the composed text, not on how any
particular screen draws it.
"""

import logging

from sqlalchemy import select

from app.models.patient import Patient
from app.models.user import User
from app.rules.safety_assessment import evaluate_patient_safety
from app.services.adherence_service import calculate_adherence_score
from conftest import register

FRESH_PATIENT = "fresh@example.com"


async def _fresh_patient_id(client, session):
    """Register a patient who has logged nothing, and return their patient id."""
    await register(client, FRESH_PATIENT)
    await session.rollback()  # see conftest._count: read the committed row, not a snapshot

    user = (
        await session.execute(select(User).where(User.email == FRESH_PATIENT))
    ).scalars().one()
    patient = (
        await session.execute(select(Patient).where(Patient.user_id == user.id))
    ).scalars().one()
    return patient.id


# ---------------------------------------------------------------------------
# The API contract
# ---------------------------------------------------------------------------


async def test_score_endpoint_reports_no_rate_rather_than_a_perfect_one(client):
    """The exact payload a client sees for a patient with no logged doses."""
    headers = await register(client, FRESH_PATIENT)

    r = await client.get("/api/v1/adherence/score", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["expected_doses"] == 0
    assert body["total_taken"] == 0
    assert body["total_missed"] == 0
    assert body["total_skipped"] == 0

    for field in ("adherence_rate", "missed_rate", "skipped_rate"):
        assert body[field] is None, (
            f"{field} came back as {body[field]!r} for a patient with no expected "
            "doses; a number here is a claim the data does not support"
        )

    assert body["trend"] == "INSUFFICIENT_DATA"
    assert body["should_escalate"] is False
    assert body["escalation_reasons"] == []


async def test_time_slot_breakdown_rates_are_null_too(client):
    """
    Per-slot rates follow the same rule.

    These are the more common case, not the edge case: a patient dosing only in the
    morning has three empty slots on every request, so ``night.adherence_rate`` was
    reporting 100% for a slot in which nothing was ever scheduled.
    """
    headers = await register(client, FRESH_PATIENT)
    body = (await client.get("/api/v1/adherence/score", headers=headers)).json()

    slots = body["time_slot_breakdown"]
    assert set(slots) == {"morning", "afternoon", "evening", "night"}
    for name, slot in slots.items():
        assert slot["total_expected"] == 0
        assert slot["adherence_rate"] is None, f"{name} claims {slot['adherence_rate']}%"

    # Day-of-week has the same shape and the same problem: a 7-day window starting
    # mid-week still lists all seven days.
    for day in body["day_of_week_breakdown"]:
        if day["total_expected"] == 0:
            assert day["adherence_rate"] is None, day["day_name"]


async def test_the_null_rates_are_documented_in_the_schema(client):
    """
    The published schema must say the field is nullable and say what null means.

    A generated client decides how to type the field from this document. If it says
    ``number`` the Dart model gets a non-nullable double and throws on the first fresh
    patient; if it says nullable but explains nothing, the next author writes
    ``rate ?? 0`` and reintroduces the original bug in the presentation layer.
    """
    spec = (await client.get("/openapi.json")).json()
    rate = spec["components"]["schemas"]["AdherenceMetricsResponse"]["properties"][
        "adherence_rate"
    ]

    # anyOf[number, null] is how Pydantic v2 renders Optional[float] in OpenAPI 3.1.
    assert "null" in str(rate), rate
    assert "not measurable" in rate.get("description", "").lower()


# ---------------------------------------------------------------------------
# The service layer
# ---------------------------------------------------------------------------


async def test_calculate_adherence_score_returns_none_not_a_number(client, session):
    """Asserted directly on the dataclass, since three other modules read it."""
    patient_id = await _fresh_patient_id(client, session)

    metrics = await calculate_adherence_score(session, patient_id, days=7)

    assert metrics.expected_doses == 0
    assert metrics.adherence_rate is None
    assert metrics.missed_rate is None
    assert metrics.skipped_rate is None
    assert metrics.trend == "INSUFFICIENT_DATA"
    assert metrics.should_escalate is False
    assert metrics.time_slot_breakdown["morning"].adherence_rate is None


async def test_safety_assessment_survives_a_null_rate(client, session, caplog):
    """
    The assessment must not raise, and must not *silently* raise.

    The adherence block in ``evaluate_patient_safety`` is wrapped in a bare
    ``except Exception``. Comparing a null rate with ``<`` raises TypeError, which that
    handler would have swallowed — so the observable result of the bug would have been
    a safety assessment that quietly stopped considering adherence at all, for every
    patient, with nothing in the response to indicate it. The handler now logs, and
    this test fails on that log record rather than on the return value, because the
    return value looks identical either way.
    """
    patient_id = await _fresh_patient_id(client, session)

    with caplog.at_level(logging.WARNING, logger="app.rules.safety_assessment"):
        assessment = await evaluate_patient_safety(db=session, patient_id=patient_id)

    assert assessment.adherence_risks == [], (
        "a patient with no doses has no adherence risk to report"
    )
    assert caplog.records == [], (
        "the adherence branch of the safety assessment failed and was swallowed: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# The composed text a person actually reads
# ---------------------------------------------------------------------------


async def test_analysis_does_not_congratulate_a_patient_with_no_history(client):
    """
    The end of the chain, and where the wrong number did the most damage.

    Every branch of the patient summary bands the patient by rate, so with no rate the
    old code fell into the top band and produced "Great work! Your medication adherence
    is at 100%". The barrier classifier's fallback did the same, reporting adherence "on
    track" as OBSERVED evidence at HIGH confidence — a clinical statement composed from
    nothing.
    """
    headers = await register(client, FRESH_PATIENT)

    r = await client.get("/api/v1/adherence/analysis", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    summary = body["patient_explanation"]["summary"].lower()
    assert "great work" not in summary
    assert "100%" not in summary
    assert "cannot be measured" in summary

    brief = body["clinical_brief"]
    assert brief["adherence_rate"] is None, (
        f"the clinician brief reports {brief['adherence_rate']}% from no data"
    )
    assert brief["insights"]["trend"] == "INSUFFICIENT_DATA"

    # The barrier list must say "no data", not "on track", and must not claim to have
    # observed anything at HIGH confidence.
    barriers = brief["insights"]["possible_barriers"]
    assert len(barriers) == 1
    barrier = barriers[0]
    assert "on track" not in barrier["observed_pattern"].lower()
    assert "none%" not in barrier["observed_pattern"].lower()
    assert barrier["status"] == "UNKNOWN"
    assert barrier["confidence"] == "LOW"

    # An empty findings list reads as "reviewed, nothing found". Say why it is empty.
    assert any(
        "not measurable" in p.lower() for p in brief["insights"]["concerning_patterns"]
    ), brief["insights"]["concerning_patterns"]
