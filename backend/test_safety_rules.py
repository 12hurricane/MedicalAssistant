import pytest
from app.rules.safety_rules import (
    assess_patient_report,
    assess_adherence_risk,
    Severity,
    SafetyAction,
)

def test_assess_patient_report_urgent():
    report = "I am having severe chest pain right now"
    assessment = assess_patient_report(report)
    
    assert assessment.severity == Severity.HIGH
    assert assessment.action == SafetyAction.URGENT_ACTION
    assert assessment.requires_human_review is True
    assert "emergency room" in assessment.recommended_message.lower()

def test_assess_patient_report_concerning():
    report = "I have a terrible persistent headache since yesterday"
    assessment = assess_patient_report(report)
    
    assert assessment.severity == Severity.MEDIUM
    assert assessment.action == SafetyAction.CONTACT_CLINICIAN
    assert assessment.requires_human_review is True
    assert "contact your healthcare provider" in assessment.recommended_message.lower()

def test_assess_patient_report_out_of_scope():
    report = "Should I stop taking my medication?"
    assessment = assess_patient_report(report)
    
    assert assessment.severity == Severity.MEDIUM
    assert assessment.action == SafetyAction.CONTACT_CLINICIAN
    assert assessment.requires_human_review is False
    assert "cannot make changes" in assessment.recommended_message.lower()

def test_assess_patient_report_low_severity():
    report = "Can you tell me how to store this medication?"
    assessment = assess_patient_report(report)
    
    assert assessment.severity == Severity.LOW
    assert assessment.action == SafetyAction.PROVIDE_INFORMATION
    assert assessment.requires_human_review is False
    assert "general information" in assessment.recommended_message.lower()

def test_assess_adherence_risk_no_response_urgent():
    assessment = assess_adherence_risk(adherence_score=80.0, consecutive_missed=0, days_no_response=3)
    
    assert assessment.severity == Severity.HIGH
    assert assessment.action == SafetyAction.URGENT_ACTION
    assert assessment.requires_human_review is True
    assert "welfare check" in assessment.recommended_message.lower()

def test_assess_adherence_risk_consecutive_missed_high():
    assessment = assess_adherence_risk(adherence_score=75.0, consecutive_missed=5, days_no_response=1)
    
    assert assessment.severity == Severity.HIGH
    assert assessment.action == SafetyAction.CONTACT_CLINICIAN
    assert assessment.requires_human_review is True
    assert "notified" in assessment.recommended_message.lower()

def test_assess_adherence_risk_low_score_medium():
    assessment = assess_adherence_risk(adherence_score=40.0, consecutive_missed=2, days_no_response=1)
    
    assert assessment.severity == Severity.MEDIUM
    assert assessment.action == SafetyAction.CONTACT_CLINICIAN
    assert assessment.requires_human_review is True
    assert "lower than expected" in assessment.recommended_message.lower()

def test_assess_adherence_risk_some_missed_medium():
    assessment = assess_adherence_risk(adherence_score=90.0, consecutive_missed=3, days_no_response=0)
    
    assert assessment.severity == Severity.MEDIUM
    assert assessment.action == SafetyAction.CONTACT_CLINICIAN
    assert assessment.requires_human_review is True
    assert "lower than expected" in assessment.recommended_message.lower()

def test_assess_adherence_risk_low_risk():
    assessment = assess_adherence_risk(adherence_score=95.0, consecutive_missed=1, days_no_response=0)
    
    assert assessment.severity == Severity.LOW
    assert assessment.action == SafetyAction.PROVIDE_INFORMATION
    assert assessment.requires_human_review is False
    assert "on track" in assessment.recommended_message.lower()
