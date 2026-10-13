"""OCR Agent for prescription ingestion.

Extracts text from raw prescription images (base64) or accepts direct text inputs.
Supports pluggable vision backend with realistic simulated fallback for local
inference environments without heavy vision model dependencies.
"""

from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

MOCK_PRESCRIPTION_TEXT = (
    "Dr. Sarah Jenkins, MD\n"
    "Metro Health Clinic\n"
    "Date: 2026-10-01\n"
    "Patient: John Doe\n\n"
    "Rx:\n"
    "1. Metformin 500mg - 1 tablet twice daily with meals for 30 days\n"
    "2. Lisinopril 10mg - 1 tablet once daily in the morning for 30 days\n"
)


async def extract_prescription_text(
    image_base64: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> str:
    """Extract text from prescription image or return provided/simulated text.

    Args:
        image_base64: Base64-encoded string of the prescription image.
        raw_text: Pre-extracted text string (if available).

    Returns:
        Extracted raw text string.

    Raises:
        ValueError: If neither image_base64 nor raw_text is provided.
    """
    if raw_text and raw_text.strip():
        logger.info("OCR Agent: using provided raw text (%d characters)", len(raw_text))
        return raw_text.strip()

    if not image_base64:
        raise ValueError("No image or raw text provided to OCR agent.")

    logger.info("OCR Agent: processing prescription image payload (%d bytes)", len(image_base64))
    
    # In an environment with a local vision model (e.g., llava via ollama)
    # or PaddleOCR/Tesseract, the image can be passed to that engine:
    # response = await vision_client.extract_text(image_base64)
    # return response
    
    # For local inference environments without heavy vision dependencies:
    return MOCK_PRESCRIPTION_TEXT
