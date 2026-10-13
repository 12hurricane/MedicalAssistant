"""Gemini API transport.

A minimal httpx async client for Google Gemini.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMUnavailable(RuntimeError):
    """Raised when the generative model cannot be reached or fails to generate a response."""

class GeminiClient:
    """Minimal client for the Google Gemini API."""

    def __init__(self) -> None:
        self.model = settings.GEMINI_MODEL
        self.api_key = settings.GEMINI_API_KEY
        self.enabled = settings.GEMINI_ENABLED
        self._client = httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT)

    async def is_available(self) -> bool:
        """True if Gemini is enabled and configured with an API key."""
        return self.enabled and bool(self.api_key)

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.2,
        format: Optional[str | dict] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Run one non-streaming completion and return the text."""
        if not await self.is_available():
            raise LLMUnavailable("Gemini API is disabled or missing API key.")

        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
            }
        }

        if format == "json":
            payload["generationConfig"]["responseMimeType"] = "application/json"
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        client_timeout = timeout or settings.GEMINI_TIMEOUT

        try:
            response = await self._client.post(
                url, json=payload, timeout=client_timeout
            )
            response.raise_for_status()
            data = response.json()
            
            try:
                # Extract text from standard Gemini response schema
                text = (data
                        .get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", ""))
                if not text:
                    raise ValueError("Empty text field in response")
                return text.strip()
            except (IndexError, KeyError, ValueError) as e:
                raise LLMUnavailable(f"Failed to parse Gemini response: {e}") from e
                
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(f"Gemini model {self.model!r} timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            # Try to extract the error message from the Gemini API
            err_msg = exc.response.text
            try:
                err_json = exc.response.json()
                if "error" in err_json and "message" in err_json["error"]:
                    err_msg = err_json["error"]["message"]
            except Exception:
                pass
            raise LLMUnavailable(
                f"Gemini returned HTTP {exc.response.status_code}: {err_msg}"
            ) from exc
        except Exception as exc:
            raise LLMUnavailable(f"Failed to communicate with Gemini: {exc}") from exc

# Module-level default
gemini_client = GeminiClient()
