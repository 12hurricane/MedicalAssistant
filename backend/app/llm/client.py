"""Ollama transport.

A thin async client over Ollama's HTTP API on loopback. No API key, no vendor account,
no per-token cost, and no patient data leaving the host — which is the reason this is
local rather than a hosted endpoint, cost being the lesser argument.

Deliberately not LangChain, despite ``langchain-ollama`` sitting in requirements.txt
unimported. This needs two calls — "is the daemon there" and "generate" — and a direct
httpx client makes the timeout, the context size and the thinking-token handling below
visible at the call site instead of behind a framework's defaults. When the agent layer
in ``app/graph`` actually needs LangGraph's orchestration, it can wrap this or replace
it; adding the abstraction before there is a second caller would be guessing at what
that caller needs.

Nothing in the request path imports this module yet.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when the local model cannot be reached or did not answer.

    A distinct type because the caller's correct response is specific: fall back to the
    deterministic output, which already exists and is already complete. A generative
    summary is an enhancement over ``adherence_analysis_service``'s composed text, so
    losing it degrades the response rather than failing the request — the same shape as
    the adherence block in ``evaluate_patient_safety``, and for the same reason.
    """


# qwen3 is a reasoning model: left alone it emits its chain of thought wrapped in
# <think> tags, inline, before the answer. That is unacceptable in a clinical brief for
# two reasons — a clinician would be reading unreviewed intermediate reasoning as though
# it were a finding, and the guardrails in app.analysis.response_validator scan the text
# they are given, so reasoning that speculates about doubling a dose would trip them or,
# worse, slip through as commentary.
#
# Handled twice on purpose. The API flag is the correct fix; the regex is because a
# model swap or an Ollama upgrade that ignores the flag would otherwise put reasoning
# into a patient-facing field silently, and this is not a failure worth discovering in
# production.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# An unterminated block means generation was cut off mid-reasoning — drop the remainder
# rather than shipping half a thought as the answer.
_THINK_OPEN = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove chain-of-thought markup from a completion."""
    text = _THINK_BLOCK.sub("", text)
    text = _THINK_OPEN.sub("", text)
    return text.strip()


class OllamaClient:
    """Minimal async client for a local Ollama daemon."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        # Generous, because this is CPU/GPU inference on the same machine serving the
        # API, not a network call to a warm datacentre. An 8B model's first token can be
        # seconds away if the weights are cold.
        self.timeout = timeout

    async def is_available(self) -> bool:
        """True if the daemon answers and has the configured model pulled.

        Checks the model too, not just the daemon. "Ollama is running" and "the model
        this deployment is configured for exists" are different facts, and the second is
        the one that decides whether a request will work — a missing model is a 404 at
        generation time, which is a confusing way to learn about a typo in .env.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                names = {m.get("name", "") for m in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("Ollama not reachable at %s: %s", self.base_url, exc)
            return False

        if self.model in names:
            return True
        logger.warning(
            "Ollama is running but model %r is not pulled. Available: %s. "
            "Run: ollama pull %s",
            self.model,
            sorted(names) or "none",
            self.model,
        )
        return False

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.2,
        num_ctx: int = 8192,
        think: bool = False,
        format: Optional[str | dict] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Run one non-streaming completion and return the text.

        ``temperature`` defaults low. This is not a creative writing task: the same
        metrics should not produce a differently-toned clinical brief on each request,
        and a clinician comparing two reviews of the same patient needs the difference
        to mean something.

        ``num_ctx`` is set explicitly rather than left to the model's default, which
        Ollama may set well below what a prompt carrying retrieved evidence plus a
        4000-character patient note needs. Silent truncation drops the *end* of the
        prompt — which, given the section order in ``prompt.py``, is the untrusted
        patient text and the trailing safety reminder.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": think,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        }
        if format:
            payload["format"] = format

        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate", json=payload
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(
                f"Local model {self.model!r} at {self.base_url} did not respond: {exc}"
            ) from exc
        except ValueError as exc:
            raise LLMUnavailable(
                f"Local model {self.model!r} returned a non-JSON body: {exc}"
            ) from exc

        text = strip_reasoning(body.get("response", ""))
        if not text:
            raise LLMUnavailable(
                f"Local model {self.model!r} returned an empty completion."
            )
        return text


# Module-level default, constructed from settings. Cheap to make — it holds no
# connection, opening one per call instead, so there is no pool to share or shut down.
ollama_client = OllamaClient()
