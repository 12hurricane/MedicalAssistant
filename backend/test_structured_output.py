import pytest
from pydantic import ValidationError
from app.analysis.schemas import GenerativeClinicalInsights, BarrierItem
import json

def test_valid_output():
    data = {
        "trend": "STABLE",
        "concerning_patterns": ["Missed 2 doses"],
        "possible_barriers": []
    }
    insights = GenerativeClinicalInsights.model_validate(data)
    assert insights.trend == "STABLE"

def test_case_a_not_json_at_all():
    text = "This is just a sentence, not JSON."
    with pytest.raises(ValidationError):
        GenerativeClinicalInsights.model_validate_json(text)

def test_case_b_markdown_fenced_json():
    text = "```json\n{\"trend\": \"STABLE\", \"concerning_patterns\": [], \"possible_barriers\": []}\n```"
    # Pydantic's model_validate_json does not strip fences.
    with pytest.raises(ValueError):
        GenerativeClinicalInsights.model_validate_json(text)

def test_case_c_truncated_json():
    text = "{\"trend\": \"STABLE\", \"concerning_pat"
    with pytest.raises(ValueError):
        GenerativeClinicalInsights.model_validate_json(text)

def test_case_d_empty_response():
    text = ""
    with pytest.raises(ValueError):
        GenerativeClinicalInsights.model_validate_json(text)

def test_missing_required_fields():
    # In GenerativeClinicalInsights, `concerning_patterns` and `possible_barriers` 
    # have default_factory=list. Are they strictly required to be provided by the LLM?
    # If the LLM omits them, Pydantic inserts [].
    # But wait, if they are meant to be required in the JSON payload, we should remove defaults.
    pass

def test_wrong_data_types():
    data = {
        "trend": 123,
        "concerning_patterns": "not a list",
        "possible_barriers": {"unexpected": "object"}
    }
    with pytest.raises(ValidationError):
        GenerativeClinicalInsights.model_validate(data)

def test_unexpected_fields():
    data = {
        "trend": "UNKNOWN",
        "concerning_patterns": [],
        "possible_barriers": [],
        "fake_clinical_decision": "START THIS MEDICATION"
    }
    # If strict/forbid is not set, this will silently pass.
    # We want it to raise ValidationError.
    with pytest.raises(ValidationError):
        GenerativeClinicalInsights.model_validate(data)

if __name__ == '__main__':
    pytest.main(['-v', __file__])
