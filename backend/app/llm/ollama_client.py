"""Ollama API transport.

A minimal httpx async client for local Ollama.
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

class OllamaClient:
    """Minimal client for the Ollama REST API."""

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL
        self._client = httpx.AsyncClient(timeout=30.0)

    async def is_available(self) -> bool:
        """True if the Ollama API is reachable and has the expected model."""
        try:
            # Check /api/tags to verify model exists (15s timeout to handle CPU spikes during generation)
            response = await self._client.get(f"{self.base_url}/api/tags", timeout=15.0)
            if response.status_code != 200:
                return False
            data = response.json()
            models = [m.get("name") for m in data.get("models", [])]
            # Some models have tags like :latest, so we check if the prefix matches
            return any(m.startswith(self.model) for m in models)
        except Exception as exc:
            logger.info("Ollama API not available: %s", exc)
            return False

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.2,
        num_ctx: int = 8192,
        format: Optional[str | dict] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Run one non-streaming completion and return the text."""
        
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
            },
        }

        if format:
            # Ollama supports passing "json" or a JSON schema dict for grammar-constrained generation
            payload["format"] = format
        
        url = f"{self.base_url}/api/generate"
        client_timeout = timeout or 30.0

        try:
            response = await self._client.post(
                url, json=payload, timeout=client_timeout
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(f"Ollama model {self.model!r} timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMUnavailable(
                f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except Exception as exc:
            raise LLMUnavailable(f"Failed to communicate with Ollama: {exc}") from exc

    async def generate_chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
        timeout: Optional[float] = None,
    ) -> str:
        """Run chat completion with messages and return the text."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        url = f"{self.base_url}/api/chat"
        client_timeout = timeout or 30.0
        try:
            response = await self._client.post(url, json=payload, timeout=client_timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "").strip()
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(f"Ollama model {self.model!r} timed out: {exc}") from exc
        except Exception as exc:
            raise LLMUnavailable(f"Failed to communicate with Ollama chat: {exc}") from exc

# Module-level default
ollama_client = OllamaClient()
