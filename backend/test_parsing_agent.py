import json
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.parsing_agent import parse_prescription_text
from app.llm.gemini_client import LLMUnavailable
from app.schemas.prescription import PrescriptionCreate

@pytest.fixture
def mock_gemini():
    with patch("app.agents.parsing_agent.gemini_client") as mock:
        mock.is_available = AsyncMock(return_value=True)
        yield mock

@pytest.mark.asyncio
async def test_parse_prescription_text_success(mock_gemini):
    valid_json = {
        "doctor_name": "Dr. Smith",
        "clinic_name": "City Clinic",
        "prescription_date": "2024-03-15",
        "medications": [
            {
                "medicine_name": "Amoxicillin",
                "strength": "500mg",
                "dose": "1 capsule",
                "frequency": "three times daily",
                "duration_days": 10,
                "instructions": "Take with food"
            }
        ]
    }
    mock_gemini.generate = AsyncMock(return_value=json.dumps(valid_json))
    
    result = await parse_prescription_text("Some OCR text about Amoxicillin.")
    
    # Verify the structure matches our expected output
    assert result["doctor_name"] == "Dr. Smith"
    assert len(result["medications"]) == 1
    assert result["medications"][0]["medicine_name"] == "Amoxicillin"

@pytest.mark.asyncio
async def test_parse_prescription_text_malformed_json_falls_back(mock_gemini):
    # Simulating a malformed response that causes JSONDecodeError
    mock_gemini.generate = AsyncMock(return_value="{ missing_quotes: ")
    
    # It should catch JSONDecodeError and use the heuristic fallback without crashing
    result = await parse_prescription_text("Dr. Fallback\n- Amoxicillin 500mg tid")
    
    # It falls back to deterministic parsing which extracts from the text
    assert result["doctor_name"] == "Dr. Fallback"
    assert result["medications"][0]["medicine_name"] == "Amoxicillin  tid"
    assert result["medications"][0]["frequency"] == "three times daily"

@pytest.mark.asyncio
async def test_parse_prescription_text_empty_response(mock_gemini):
    # Simulating an empty string from gemini (handled by our new explicit check)
    mock_gemini.generate = AsyncMock(return_value="")
    
    result = await parse_prescription_text("Dr. Empty\n- Lisinopril 10mg once daily")
    
    assert result["doctor_name"] == "Dr. Empty"
    assert result["medications"][0]["medicine_name"] == "Lisinopril  once daily"
