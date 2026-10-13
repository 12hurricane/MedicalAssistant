"""LLM Router with Generative Fallback Architecture.

Cascade Priority:
Tier 1: Groq LPU (qwen/qwen3.8-27b) - Fast Path (~1.0 - 1.5s)
Tier 2: Hugging Face (meta-llama/Llama-3.1-8B-Instruct) - Cloud fallback
Tier 3: Google Gemini API - Commercial cloud backup
Tier 4: Local Ollama (llama3.2 / phi3) - Zero-internet offline safety net (~16s)
"""

import os
import logging
from typing import Optional

from app.services.groq_client import GroqClient
from app.services.huggingface_client import HuggingFaceClient
from app.llm.gemini_client import gemini_client, LLMUnavailable as GeminiUnavailable
from app.llm.ollama_client import ollama_client, LLMUnavailable as OllamaUnavailable

logger = logging.getLogger(__name__)

groq_client = GroqClient()
hf_client = HuggingFaceClient()

class LLMUnavailable(RuntimeError):
    """Raised when all generative models fail."""

class LLMRouter:
    def __init__(self):
        self.groq_client = groq_client
        self.hf_client = hf_client
        self.gemini_client = gemini_client
        self.ollama_client = ollama_client

    async def generate_response(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 600
    ) -> str:
        # ---------------------------------------------------------
        # TIER 1: Groq LPU (Fast Path ~1.5s)
        # ---------------------------------------------------------
        if self.groq_client and await self.groq_client.is_available():
            try:
                logger.info("Routing to Tier 1: Groq LPU...")
                return await self.groq_client.generate_response(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            except Exception as e:
                logger.warning(f"Tier 1 (Groq) failed: {e}. Cascading to Tier 2 (Hugging Face)...")

        # ---------------------------------------------------------
        # TIER 2: Hugging Face Serverless Router
        # ---------------------------------------------------------
        if self.hf_client and (self.hf_client.token or os.getenv("HF_TOKEN")):
            try:
                logger.info("Routing to Tier 2: Hugging Face Router...")
                return await self.hf_client.generate_response(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            except Exception as e:
                logger.warning(f"Tier 2 (Hugging Face) failed: {e}. Cascading to Tier 3 (Gemini)...")

        # ---------------------------------------------------------
        # TIER 3: Gemini API (Cloud Backup)
        # ---------------------------------------------------------
        if self.gemini_client and await self.gemini_client.is_available():
            try:
                logger.info("Routing to Tier 3: Gemini...")
                prompt = "\n".join(m.get("content", "") for m in messages)
                return await self.gemini_client.generate(prompt=prompt, temperature=temperature)
            except Exception as e:
                logger.warning(f"Tier 3 (Gemini) failed: {e}. Cascading to Tier 4 (Local Ollama)...")

        # ---------------------------------------------------------
        # TIER 4: Local Ollama (Offline Safety Net)
        # ---------------------------------------------------------
        if self.ollama_client and await self.ollama_client.is_available():
            try:
                logger.info("Routing to Tier 4: Local Ollama (Offline)...")
                return await self.ollama_client.generate_chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            except Exception as e:
                logger.error(f"All LLM tiers failed. Last error (Ollama): {e}")
                raise LLMUnavailable(f"All generative AI tiers failed to respond: {e}") from e

        raise LLMUnavailable("All generative AI models (Groq, HF, Gemini, Ollama) failed or are unavailable.")

llm_router = LLMRouter()

async def get_generative_response(
    prompt: str,
    *,
    format: Optional[str | dict] = None,
    timeout: Optional[float] = None,
    temperature: Optional[float] = None,
) -> tuple[str, str]:
    """Get a response from the generative model router.
    
    Priority cascade:
    1. Groq LPU (GENERATED_GROQ)
    2. Hugging Face (GENERATED_HF)
    3. Gemini (GENERATED_GEMINI)
    4. Ollama (GENERATED_OLLAMA)
    
    Returns a tuple of (response_text, generation_status).
    Raises LLMUnavailable if all fail.
    """
    messages = [{"role": "user", "content": prompt}]
    temp = temperature if temperature is not None else 0.1

    # ---------------------------------------------------------
    # TIER 1: Groq LPU (Fast Path ~1.0 - 1.5s)
    # ---------------------------------------------------------
    if await groq_client.is_available():
        try:
            logger.info("Attempting generative call with Groq (Tier 1)...")
            text = await groq_client.generate_response(messages=messages, temperature=temp)
            logger.info("Groq generation successful.")
            return text, "GENERATED_GROQ"
        except Exception as groq_exc:
            logger.warning(f"Groq generation failed: {groq_exc}. Falling back to Hugging Face...")
    else:
        logger.warning("Groq not configured or available. Falling back to Hugging Face...")

    # ---------------------------------------------------------
    # TIER 2: Hugging Face (Cloud Fallback)
    # ---------------------------------------------------------
    try:
        logger.info("Attempting generative call with Hugging Face (Tier 2)...")
        hf_temp = temperature if temperature is not None else 0.2
        text = await hf_client.generate_response(messages=messages, temperature=hf_temp)
        logger.info("Hugging Face generation successful.")
        return text, "GENERATED_HF"
    except Exception as hf_exc:
        logger.warning(f"Hugging Face generation failed: {hf_exc}. Falling back to Gemini...")

    # ---------------------------------------------------------
    # TIER 3: Google Gemini (Commercial Cloud Backup)
    # ---------------------------------------------------------
    if await gemini_client.is_available():
        try:
            logger.info("Attempting generative call with Gemini (Tier 3)...")
            text = await gemini_client.generate(prompt=prompt, format=format, timeout=timeout)
            logger.info("Gemini generation successful.")
            return text, "GENERATED_GEMINI"
        except GeminiUnavailable as exc:
            logger.warning(f"Gemini generation failed: {exc}. Falling back to Ollama...")
        except Exception as gemini_exc:
            logger.warning(f"Gemini call error: {gemini_exc}. Falling back to Ollama...")
    else:
        logger.warning("Gemini not configured or available. Falling back to Ollama...")

    # ---------------------------------------------------------
    # TIER 4: Local Ollama (Zero-Internet Offline Safety Net)
    # ---------------------------------------------------------
    if await ollama_client.is_available():
        try:
            logger.info("Attempting generative call with Ollama (Tier 4)...")
            gen_kwargs = {}
            if temperature is not None:
                gen_kwargs["temperature"] = temperature
            text = await ollama_client.generate(prompt=prompt, format=format, timeout=timeout, **gen_kwargs)
            logger.info("Ollama generation successful.")
            return text, "GENERATED_OLLAMA"
        except OllamaUnavailable as exc:
            logger.error(f"Ollama generation failed: {exc}")
            raise LLMUnavailable("All models (Groq, HF, Gemini, Ollama) failed to generate a response.") from exc
    else:
        logger.warning("Ollama not available.")

    raise LLMUnavailable("All models (Groq, HF, Gemini, Ollama) failed or are unavailable.")
