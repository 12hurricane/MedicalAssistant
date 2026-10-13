import pytest
from pydantic import ValidationError
from app.analysis.schemas import GenerativeClinicalInsights

def test_nested_unexpected_fields():
    # Test valid
    valid_data = {
        "trend": "UNKNOWN",
        "concerning_patterns": [],
        "possible_barriers": [
            {
                "category": "Forgetfulness",
                "status": "OBSERVED",
                "confidence": "HIGH",
                "observed_pattern": "x",
                "hypothesis_rationale": "y",
                "follow_up_question": "z",
                "patient_reported_text": None
            }
        ]
    }
    GenerativeClinicalInsights.model_validate(valid_data)
    
    # Test invalid nested
    invalid_nested_data = {
        "trend": "UNKNOWN",
        "concerning_patterns": [],
        "possible_barriers": [
            {
                "category": "Forgetfulness",
                "status": "OBSERVED",
                "confidence": "HIGH",
                "observed_pattern": "x",
                "hypothesis_rationale": "y",
                "follow_up_question": "z",
                "patient_reported_text": None,
                "some_fake_field": "123"
            }
        ]
    }
    with pytest.raises(ValidationError) as exc:
        GenerativeClinicalInsights.model_validate(invalid_nested_data)
    assert "Extra inputs are not permitted" in str(exc.value)

def test_type_coercion():
    # String where list is expected -> ValidationError
    with pytest.raises(ValidationError):
        GenerativeClinicalInsights.model_validate({
            "trend": "UNKNOWN",
            "concerning_patterns": "not a list",
            "possible_barriers": []
        })

    # Object where list is expected -> ValidationError
    with pytest.raises(ValidationError):
        GenerativeClinicalInsights.model_validate({
            "trend": "UNKNOWN",
            "concerning_patterns": {"key": "value"},
            "possible_barriers": []
        })

if __name__ == '__main__':
    pytest.main(['-v', __file__])
