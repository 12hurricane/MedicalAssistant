"""
Master Safety Assessment Engine

Coordinates the full deterministic safety evaluation pipeline:
1. Canonical Drug Normalization
2. Pairwise Drug-Drug Interaction Detection
3. Allergy Contraindications
4. Disease / Chronic Condition Contraindications
5. Duplicate Therapy Detection
6. Adherence Safety & Clinical Follow-up Triggers
"""

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.models.prescribed_medication import PrescribedMedication
from app.models.types import utcnow
from app.rules.drug_normalizer import CanonicalDrug, normalize_drug
from app.rules.interaction_engine import (
    InteractionSeverity,
    MedicationInteractionAlert,
    check_drug_interactions,
)
from app.rules.contraindication_engine import (
    ContraindicationAlert,
    ContraindicationSeverity,
    DuplicateTherapyAlert,
    check_allergy_contraindications,
    check_condition_contraindications,
    check_duplicate_therapies,
)
from app.services import adherence_service
from app.services.adherence_service import rate_below

logger = logging.getLogger(__name__)


@dataclass
class AdherenceSafetyAlert:
    """Safety alert derived from patient medication adherence patterns.

    ``adherence_rate`` is a plain float, not Optional, and deliberately so: this alert
    is only ever constructed behind an ``expected_doses >= 3`` guard, so a measurable
    rate is a precondition of the alert existing at all. An adherence *risk* inferred
    from no adherence data would not be a finding, it would be a guess.
    """
    adherence_rate: float
    consecutive_missed: int
    critical_drugs_affected: List[str]
    clinical_risk: str
    recommended_action: str


@dataclass
class SafetyEvidence:
    """Structured evidence item supporting the clinical safety determination."""
    category: str
    finding: str
    severity: str
    reference_source: str


@dataclass
class SafetyAssessment:
    """Master clinical safety evaluation contract."""
    patient_id: int
    evaluated_at: datetime
    risk_level: str  # "LOW", "MODERATE", "HIGH", "CRITICAL"
    requires_human_review: bool
    recommended_action: str
    medication_interactions: List[MedicationInteractionAlert] = field(default_factory=list)
    contraindications: List[ContraindicationAlert] = field(default_factory=list)
    duplicate_therapies: List[DuplicateTherapyAlert] = field(default_factory=list)
    adherence_risks: List[AdherenceSafetyAlert] = field(default_factory=list)
    evidence: List[SafetyEvidence] = field(default_factory=list)


async def evaluate_patient_safety(
    db: AsyncSession,
    patient_id: int,
    proposed_medications: Optional[List[str]] = None,
) -> SafetyAssessment:
    """
    Perform an exhaustive, deterministic clinical safety assessment for a patient.
    
    Evaluates currently active prescribed medications, any newly proposed drug names,
    patient allergies, chronic conditions, and recent adherence performance.
    """
    now = utcnow()

    # 1. Fetch Patient
    patient = await db.get(Patient, patient_id)
    if not patient:
        return SafetyAssessment(
            patient_id=patient_id,
            evaluated_at=now,
            risk_level="LOW",
            requires_human_review=False,
            recommended_action="Patient not found.",
        )

    # 2. Fetch Active Prescribed Medications
    stmt = (
        select(PrescribedMedication)
        .where(
            PrescribedMedication.patient_id == patient_id,
            PrescribedMedication.is_active.is_(True),
        )
    )
    result = await db.execute(stmt)
    active_prescribed = result.scalars().all()

    # Normalize active medications
    all_drugs: List[CanonicalDrug] = []
    seen_ids = set()

    for pmed in active_prescribed:
        cdrug = normalize_drug(pmed.medicine_name)
        if cdrug.canonical_id not in seen_ids:
            all_drugs.append(cdrug)
            seen_ids.add(cdrug.canonical_id)

    # Add any proposed medications (e.g. from prescription verification / what-if check)
    if proposed_medications:
        for pmed_name in proposed_medications:
            cdrug = normalize_drug(pmed_name)
            if cdrug.canonical_id not in seen_ids:
                all_drugs.append(cdrug)
                seen_ids.add(cdrug.canonical_id)

    # 3. Check Drug Interactions
    interaction_alerts = check_drug_interactions(all_drugs)

    # 4. Check Allergy Contraindications
    allergies = patient.allergies or []
    allergy_alerts = check_allergy_contraindications(all_drugs, allergies)

    # 5. Check Condition Contraindications
    conditions = patient.chronic_conditions or []
    condition_alerts = check_condition_contraindications(all_drugs, conditions)
    contraindication_alerts = allergy_alerts + condition_alerts

    # 6. Check Duplicate Therapies
    duplicate_alerts = check_duplicate_therapies(all_drugs)

    # 7. Check Adherence Safety Connection
    adherence_alerts: List[AdherenceSafetyAlert] = []
    try:
        adh_metrics = await adherence_service.calculate_adherence_score(db, patient_id, days=7)
        critical_drugs = [d.generic_name.title() for d in all_drugs if d.is_critical]

        # Connect low adherence on critical drugs to clinical follow-up.
        #
        # The denominator guard is stated FIRST, on its own line. It used to be the last
        # clause of a single `and` chain, so `adh_metrics.adherence_rate < 70.0` was
        # evaluated before anything established that a rate existed. Once rates became
        # nullable that ordering was a TypeError for every patient with no logged doses
        # — raised inside the `except Exception` below, which would have silently
        # dropped adherence out of every safety assessment with no log line to find it
        # by. Ordering is load-bearing here, so it is not left to short-circuiting.
        if adh_metrics.expected_doses >= 3 and (
            rate_below(adh_metrics.adherence_rate, 70.0) or adh_metrics.should_escalate
        ):
            risk_desc = (
                f"Low 7-day adherence ({adh_metrics.adherence_rate}%) "
                f"with {adh_metrics.total_missed} missed doses."
            )
            if critical_drugs:
                risk_desc += f" Regimen includes critical medications: {', '.join(critical_drugs)}."

            adherence_alerts.append(
                AdherenceSafetyAlert(
                    adherence_rate=adh_metrics.adherence_rate,
                    consecutive_missed=max(
                        (int(reason.split()[2]) for reason in adh_metrics.escalation_reasons if "consecutive" in reason),
                        default=0,
                    ),
                    critical_drugs_affected=critical_drugs,
                    clinical_risk=risk_desc,
                    recommended_action="Schedule clinician/care-coordinator follow-up review for adherence barrier assessment.",
                )
            )
    except Exception as exc:
        # Adherence is one input to the assessment, not all of it, so a failure here
        # degrades the result rather than failing the request. It is logged, though:
        # the previous bare `pass` meant an exception in this block removed adherence
        # from every safety assessment and produced no evidence that it had.
        logger.warning(
            "Adherence safety evaluation failed for patient %s; the assessment below "
            "excludes adherence risk. %s: %s",
            patient_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )

    # 8. Compile Structured Evidence
    evidence: List[SafetyEvidence] = []

    for alert in interaction_alerts:
        evidence.append(
            SafetyEvidence(
                category="DRUG_INTERACTION",
                finding=f"Interaction between {alert.drug_a} and {alert.drug_b}: {alert.clinical_effect}",
                severity=alert.severity.value,
                reference_source=alert.source,
            )
        )

    for alert in contraindication_alerts:
        evidence.append(
            SafetyEvidence(
                category="CONTRAINDICATION",
                finding=f"{alert.medication} contraindicated with {alert.trigger} ({alert.contraindication_type}): {alert.clinical_risk}",
                severity=alert.severity.value,
                reference_source="Clinical Practice Guidelines",
            )
        )

    for alert in duplicate_alerts:
        evidence.append(
            SafetyEvidence(
                category="DUPLICATE_THERAPY",
                finding=f"Duplicate {alert.drug_class} therapy: {', '.join(alert.medications)}.",
                severity=alert.severity.value,
                reference_source="Therapeutic Duplication Safety Rules",
            )
        )

    for alert in adherence_alerts:
        evidence.append(
            SafetyEvidence(
                category="ADHERENCE_RISK",
                finding=alert.clinical_risk,
                severity="HIGH" if alert.critical_drugs_affected else "MODERATE",
                reference_source="Deterministic Adherence Metrics Engine",
            )
        )

    # 9. Compute Overall Risk Level & Clinical Action
    has_contraindication = any(
        a.severity == InteractionSeverity.CONTRAINDICATED for a in interaction_alerts
    ) or any(
        a.severity == ContraindicationSeverity.CONTRAINDICATED for a in contraindication_alerts
    )

    has_major_interaction = any(
        a.severity == InteractionSeverity.MAJOR for a in interaction_alerts
    ) or any(
        a.severity == ContraindicationSeverity.MAJOR for a in contraindication_alerts
    ) or any(
        a.severity == ContraindicationSeverity.MAJOR for a in duplicate_alerts
    )

    has_moderate_alert = bool(interaction_alerts or contraindication_alerts or duplicate_alerts or adherence_alerts)

    if has_contraindication:
        risk_level = "CRITICAL"
        requires_human_review = True
        recommended_action = (
            "BLOCK / URGENT REVIEW: Regimen contains strictly contraindicated drug combination or allergy conflict. "
            "Prescription must be reviewed and modified by a clinician before dispensing."
        )
    elif has_major_interaction:
        risk_level = "HIGH"
        requires_human_review = True
        recommended_action = (
            "ALERT / CLINICAL REVIEW REQUIRED: Major clinical drug interaction or organ risk detected. "
            "Clinician review and dosage/therapeutic adjustment recommended."
        )
    elif has_moderate_alert:
        risk_level = "MODERATE"
        requires_human_review = bool(adherence_alerts)
        recommended_action = (
            "INFORMATIONAL ALERT: Moderate interaction or adherence pattern detected. "
            "Monitor patient symptoms and provide educational guidance."
        )
    else:
        risk_level = "LOW"
        requires_human_review = False
        recommended_action = "No significant drug interactions, contraindications, or adherence risks identified."

    return SafetyAssessment(
        patient_id=patient_id,
        evaluated_at=now,
        risk_level=risk_level,
        requires_human_review=requires_human_review,
        recommended_action=recommended_action,
        medication_interactions=interaction_alerts,
        contraindications=contraindication_alerts,
        duplicate_therapies=duplicate_alerts,
        adherence_risks=adherence_alerts,
        evidence=evidence,
    )
