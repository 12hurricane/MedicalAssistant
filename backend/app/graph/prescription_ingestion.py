"""LangGraph Workflow for Prescription Ingestion & Clinical Safety Verification.

Multi-agent pipeline:
1. OCR Agent: Extracts raw text from prescription image (or simulation).
2. Parsing Agent: Parses OCR text into structured PrescriptionCreate schema via LLM.
3. Safety Agent: Performs deterministic clinical safety evaluation (allergies,
   conditions, drug-drug interactions, duplicate therapies, polypharmacy).
"""

import logging
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.ocr_agent import extract_prescription_text
from app.agents.parsing_agent import parse_prescription_text
from app.agents.safety_agent import verify_prescription_safety

logger = logging.getLogger(__name__)


class PrescriptionState(TypedDict, total=False):
    image_base64: Optional[str]
    raw_ocr_text: Optional[str]
    patient_id: Optional[int]
    patient_allergies: Optional[List[str]]
    patient_conditions: Optional[List[str]]
    existing_medications: Optional[List[str]]
    parsed_prescription: Optional[Dict[str, Any]]
    is_safe: bool
    risk_level: str
    safety_findings: List[str]
    error: Optional[str]


async def ocr_node(state: PrescriptionState) -> Dict[str, Any]:
    """Node 1: Extract text from image or raw text."""
    logger.info("Executing OCR Node")
    try:
        raw_text = await extract_prescription_text(
            image_base64=state.get("image_base64"),
            raw_text=state.get("raw_ocr_text"),
        )
        return {"raw_ocr_text": raw_text}
    except Exception as exc:
        logger.error("OCR Node error: %s", exc)
        return {"error": f"OCR extraction failed: {exc}"}


async def parsing_node(state: PrescriptionState) -> Dict[str, Any]:
    """Node 2: Parse raw OCR text into structured schema."""
    logger.info("Executing Parsing Node")
    if state.get("error"):
        return {}

    raw_text = state.get("raw_ocr_text")
    if not raw_text:
        return {"error": "No OCR text available for parsing"}

    try:
        parsed = await parse_prescription_text(raw_text)
        return {"parsed_prescription": parsed}
    except Exception as exc:
        logger.error("Parsing Node error: %s", exc)
        return {"error": f"Prescription parsing failed: {exc}"}


async def safety_node(state: PrescriptionState) -> Dict[str, Any]:
    """Node 3: Verify clinical safety and drug interactions."""
    logger.info("Executing Safety Node")
    if state.get("error"):
        return {}

    parsed = state.get("parsed_prescription")
    if not parsed or "medications" not in parsed:
        return {
            "is_safe": False,
            "risk_level": "CRITICAL",
            "safety_findings": ["No parsed medications found in prescription"],
        }

    medications = parsed["medications"]
    safety_result = verify_prescription_safety(
        new_medications=medications,
        patient_allergies=state.get("patient_allergies"),
        patient_conditions=state.get("patient_conditions"),
        existing_medications=state.get("existing_medications"),
    )
    return {
        "is_safe": safety_result["is_safe"],
        "risk_level": safety_result["risk_level"],
        "safety_findings": safety_result["safety_findings"],
    }


def route_after_ocr(state: PrescriptionState) -> str:
    """Route to parse if OCR succeeded, else abort."""
    if state.get("error") or not state.get("raw_ocr_text"):
        return END
    return "parse"


def route_after_parse(state: PrescriptionState) -> str:
    """Route to safety if parsing succeeded, else abort."""
    if state.get("error") or not state.get("parsed_prescription"):
        return END
    return "safety"


def build_prescription_graph() -> Any:
    """Build and compile the prescription ingestion StateGraph."""
    workflow = StateGraph(PrescriptionState)

    workflow.add_node("ocr", ocr_node)
    workflow.add_node("parse", parsing_node)
    workflow.add_node("safety", safety_node)

    workflow.set_entry_point("ocr")
    workflow.add_conditional_edges("ocr", route_after_ocr, {"parse": "parse", END: END})
    workflow.add_conditional_edges("parse", route_after_parse, {"safety": "safety", END: END})
    workflow.add_edge("safety", END)

    return workflow.compile()


prescription_orchestrator = build_prescription_graph()
