"""
Deterministic safety rules: normalization, interactions, contraindications and the
adherence bridge.

Converted from a standalone ``run_safety_tests()`` script. Two problems with the
original beyond not being collected by pytest:

- It ran against ``medication.db`` through ``AsyncSessionLocal``, and to make itself
  re-runnable it *deleted every PrescribedMedication and MedicationEvent belonging
  to its patient* before seeding. Pointed at real data that is destruction of the
  adherence history this project exists to keep. Per-test databases remove both the
  need for the cleanup and the risk.
- Every assertion checked that a flag *fires*. Nothing checked that flags stay
  silent, so an engine that returned CRITICAL for every patient would have passed
  the entire suite. The two negative controls here
  (``test_unrelated_pair_produces_no_interaction_alert``,
  ``test_patient_with_no_conflicts_is_not_escalated``) close that gap: without
  them the positive cases prove much less than they appear to.
"""

from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    MedicationEvent,
    MedicationEventStatus,
    MedicationSchedule,
    Patient,
    PrescribedMedication,
    Prescription,
    ScheduleLifecycle,
    User,
)
from app.rules.contraindication_engine import (
    ContraindicationSeverity,
    check_allergy_contraindications,
    check_condition_contraindications,
    check_duplicate_therapies,
)
from app.rules.drug_normalizer import normalize_drug
from app.rules.interaction_engine import InteractionSeverity, check_drug_interactions
from app.rules.safety_assessment import evaluate_patient_safety


# --------------------------------------------------------------------------
# Drug identity
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_name, canonical_id, drug_class",
    [
        ("Glucophage 500mg", "metformin", "biguanide"),
        ("Coumadin 5 mg tablet", "warfarin", "anticoagulant"),
        ("Viagra 100mg", "sildenafil", "pde5_inhibitor"),
        ("Nitrostat 0.4mg SL", "nitroglycerin", "nitrate"),
        ("Advil 200 mg", "ibuprofen", "nsaid"),
        ("Aleve 220mg", "naproxen", "nsaid"),
        ("Augmentin 625mg", "amoxicillin_clavulanate", "penicillin_antibiotic"),
        ("Inderal 40mg", "propranolol", "non_selective_beta_blocker"),
    ],
)
def test_brand_name_normalizes_to_canonical_drug_and_class(
    raw_name, canonical_id, drug_class
):
    """
    Brand name, strength and form all reduce to one canonical identity.

    Every rule downstream matches on ``canonical_id`` and ``drug_class``, so this is
    load-bearing: if "Viagra 100mg" fails to resolve to sildenafil, the
    nitrate interaction below simply never fires and the patient sees no warning.
    A prescription image says "Viagra", never "sildenafil".
    """
    canonical = normalize_drug(raw_name)

    assert canonical.canonical_id == canonical_id, (
        f"{raw_name!r} resolved to {canonical.canonical_id!r}"
    )
    assert canonical.drug_class == drug_class, (
        f"{raw_name!r} classed as {canonical.drug_class!r}"
    )


# --------------------------------------------------------------------------
# Drug-drug interactions
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "drug_a, drug_b, expected_severity",
    [
        # Nitric-oxide potentiation: refractory hypotension.
        ("Viagra 50mg", "Nitrostat 0.4mg", InteractionSeverity.CONTRAINDICATED),
        # Additive bleeding risk.
        ("Coumadin 5mg", "Aspirin 81mg", InteractionSeverity.MAJOR),
        # Hyperkalemia.
        ("Zestril 10mg", "Aldactone 25mg", InteractionSeverity.MAJOR),
    ],
)
def test_interacting_pair_is_flagged_with_expected_severity(
    drug_a, drug_b, expected_severity
):
    """Each documented pair produces exactly one alert at the documented severity."""
    alerts = check_drug_interactions([normalize_drug(drug_a), normalize_drug(drug_b)])

    assert len(alerts) == 1, (
        f"{drug_a} + {drug_b} produced {len(alerts)} alerts: "
        f"{[(a.rule_id, a.severity) for a in alerts]}"
    )
    assert alerts[0].severity == expected_severity, alerts[0].severity
    assert alerts[0].clinical_effect, "alert has no clinical effect text to show anyone"


def test_unrelated_pair_produces_no_interaction_alert():
    """
    Negative control. Metformin and lisinopril are routinely co-prescribed to the
    same diabetic hypertensive patient and have no interaction rule.

    Without this, an engine that flagged every pair would pass the three positive
    cases above. It would also be clinically worse than useless: alert fatigue means
    a spurious warning on a normal combination trains people to dismiss the real
    contraindication when it appears.
    """
    alerts = check_drug_interactions(
        [normalize_drug("Glucophage 500mg"), normalize_drug("Zestril 10mg")]
    )

    assert alerts == [], (
        "a benign combination was flagged: "
        f"{[(a.rule_id, a.severity, a.clinical_effect) for a in alerts]}"
    )


# --------------------------------------------------------------------------
# Patient-specific contraindications
# --------------------------------------------------------------------------

def test_allergy_contraindication_is_flagged():
    """A recorded penicillin allergy contraindicates amoxicillin."""
    alerts = check_allergy_contraindications(
        [normalize_drug("Amoxicillin 500mg")], ["Penicillin"]
    )

    assert len(alerts) == 1, [a.trigger for a in alerts]
    assert alerts[0].severity == ContraindicationSeverity.CONTRAINDICATED
    assert alerts[0].clinical_risk


@pytest.mark.parametrize(
    "medicine, condition, expected_severity",
    [
        # Non-selective beta blockade in asthma: bronchospasm.
        ("Inderal 40mg", "Asthma", ContraindicationSeverity.CONTRAINDICATED),
        # NSAID in CKD: further renal impairment.
        ("Advil 400mg", "Chronic Kidney Disease", ContraindicationSeverity.MAJOR),
    ],
)
def test_condition_contraindication_is_flagged(medicine, condition, expected_severity):
    """
    A chronic condition on the patient record contraindicates the drug.

    The severities differ deliberately and are asserted exactly: collapsing MAJOR
    into CONTRAINDICATED (or the reverse) changes whether the system blocks or
    merely warns.
    """
    alerts = check_condition_contraindications([normalize_drug(medicine)], [condition])

    assert len(alerts) == 1, [a.trigger for a in alerts]
    assert alerts[0].severity == expected_severity, alerts[0].severity


def test_duplicate_nsaid_therapy_is_flagged():
    """
    Two drugs from one class is a hazard even though neither is contraindicated.

    Ibuprofen and naproxen individually pass every check above. Together they are
    double NSAID exposure, which no pairwise interaction rule catches — this is a
    distinct detector, not a special case of the interaction matrix.
    """
    alerts = check_duplicate_therapies(
        [normalize_drug("Advil 400mg"), normalize_drug("Aleve 220mg")]
    )

    assert len(alerts) == 1, [a.medications for a in alerts]
    assert alerts[0].severity == ContraindicationSeverity.MAJOR
    assert len(alerts[0].medications) == 2, alerts[0].medications


# --------------------------------------------------------------------------
# Full assessment against the database
# --------------------------------------------------------------------------

async def _seed_patient(session, *, email, allergies, conditions, medicines):
    """
    A verified prescription for ``medicines`` belonging to a patient with the given
    allergies and conditions. Returns the patient id and the created medication rows.
    """
    user = User(
        name="Safety Test Patient",
        email=email,
        # No login happens here, so the bcrypt round trip is skipped.
        hashed_password="not-a-real-hash",
        role="PATIENT",
    )
    user.patient = Patient(
        date_of_birth=date(1975, 8, 10),
        allergies=allergies,
        chronic_conditions=conditions,
        preferred_language="en",
        timezone="Asia/Kolkata",
    )
    session.add(user)
    await session.flush()
    patient = user.patient

    presc = Prescription(
        patient_id=patient.id,
        doctor_name="Dr. Gregory",
        clinic_name="Clinical Safety Center",
        prescription_date=date.today(),
        verification_status="VERIFIED",
    )
    session.add(presc)
    await session.flush()

    meds = [
        PrescribedMedication(
            prescription_id=presc.id,
            patient_id=patient.id,
            medicine_name=name,
            frequency=freq,
            is_active=True,
        )
        for name, freq in medicines
    ]
    session.add_all(meds)
    await session.commit()
    return patient.id, meds


async def test_full_assessment_escalates_to_critical_and_bridges_adherence(session):
    """
    The master assessment combines every detector above plus adherence history.

    This patient is deliberately stacked: warfarin (poorly taken), propranolol
    against recorded asthma, amoxicillin against a recorded penicillin allergy, and
    a proposed sildenafil + nitrate pair. The point is not that any single rule
    fires — those are covered individually — but that the assessment aggregates
    findings from independent detectors into one verdict, and that low adherence on
    a high-risk drug surfaces as a safety finding rather than only a metric.
    """
    patient_id, meds = await _seed_patient(
        session,
        email="safety_eval_patient@example.com",
        allergies=["Penicillin"],
        conditions=["Asthma", "Hypertension"],
        medicines=[
            ("Coumadin 5mg", "once daily"),
            ("Inderal 40mg", "twice daily"),
            ("Amoxicillin 500mg", "three times daily"),
        ],
    )
    warfarin = meds[0]

    schedule = MedicationSchedule(
        prescribed_medication_id=warfarin.id,
        patient_id=patient_id,
        scheduled_time=time(20, 0),
        start_date=date.today() - timedelta(days=7),
        status=ScheduleLifecycle.ACTIVE.value,
    )
    session.add(schedule)
    await session.flush()

    # Five days of the warfarin dose: taken twice, then missed three times.
    for offset in range(5):
        missed = offset >= 2
        at = datetime.combine(
            date.today() - timedelta(days=5 - offset), time(20, 0), tzinfo=timezone.utc
        )
        session.add(
            MedicationEvent(
                schedule_id=schedule.id,
                patient_id=patient_id,
                scheduled_at=at,
                status=(
                    MedicationEventStatus.MISSED.value
                    if missed
                    else MedicationEventStatus.TAKEN.value
                ),
                recorded_by="SYSTEM" if missed else "PATIENT",
            )
        )
    await session.commit()

    assessment = await evaluate_patient_safety(
        session, patient_id, proposed_medications=["Viagra 50mg", "Nitrostat 0.4mg"]
    )

    assert assessment.risk_level == "CRITICAL", (
        f"expected CRITICAL, got {assessment.risk_level}; findings were "
        f"{[(e.category, e.severity, e.finding) for e in assessment.evidence]}"
    )
    assert assessment.requires_human_review is True
    assert assessment.recommended_action, "no action was recommended for a CRITICAL case"

    # Penicillin allergy + asthma, at minimum.
    assert len(assessment.contraindications) >= 2, [
        (c.medication, c.trigger) for c in assessment.contraindications
    ]
    # The proposed sildenafil + nitrate pair.
    assert len(assessment.medication_interactions) >= 1, [
        (i.drug_a, i.drug_b) for i in assessment.medication_interactions
    ]
    # The adherence bridge: missed warfarin doses are a safety finding, not just a
    # number on a dashboard.
    assert len(assessment.adherence_risks) >= 1, (
        "three missed warfarin doses did not surface as an adherence safety risk"
    )


async def test_patient_with_no_conflicts_is_not_escalated(session):
    """
    Negative control for the whole assessment.

    Metformin plus lisinopril, no allergies, no contraindicating conditions, no
    missed doses. Every positive assertion in the test above would also hold for an
    engine hard-wired to return CRITICAL; this is what makes them meaningful.

    Clinically the stake is the same as the interaction control: a system that
    escalates every patient gets ignored, and then it escalates the one who mattered
    and is ignored then too.
    """
    patient_id, _ = await _seed_patient(
        session,
        email="safety_clean_patient@example.com",
        allergies=[],
        conditions=["Type 2 Diabetes"],
        medicines=[("Glucophage 500mg", "twice daily"), ("Zestril 10mg", "once daily")],
    )

    assessment = await evaluate_patient_safety(session, patient_id)

    assert assessment.risk_level != "CRITICAL", (
        "a patient with no conflicts was escalated to CRITICAL: "
        f"{[(e.category, e.severity, e.finding) for e in assessment.evidence]}"
    )
    assert assessment.requires_human_review is False, (
        "a clean patient was routed to human review: "
        f"{[(e.category, e.finding) for e in assessment.evidence]}"
    )
    assert assessment.medication_interactions == []
    assert assessment.contraindications == []

    # The patient exists and was really evaluated, rather than silently skipped.
    stored = (
        await session.execute(
            select(PrescribedMedication).where(
                PrescribedMedication.patient_id == patient_id
            )
        )
    ).scalars().all()
    assert len(stored) == 2, stored
