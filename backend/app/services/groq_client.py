import os
import re
import asyncio
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class GroqClient:
    """Async client for Groq Chat Completions API with ultra-low latency LPUs."""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model = os.getenv("GROQ_MODEL") or "qwen/qwen3.8-27b"
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"

    async def is_available(self) -> bool:
        """Check if Groq API key is present."""
        key = self.api_key or os.getenv("GROQ_API_KEY")
        return bool(key and key.startswith("gsk_"))

    async def generate_response(self, messages, temperature=0.1, max_tokens=400) -> str:
        key = self.api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY is not configured in backend environment.")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.endpoint, headers=headers, json=payload)
            if resp.status_code == 429:
                logger.warning("Groq 429 rate limit encountered. Waiting 2.5s for brief backoff...")
                await asyncio.sleep(2.5)
                resp = await client.post(self.endpoint, headers=headers, json=payload)

            if resp.status_code != 200:
                logger.error(f"Groq API returned {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            # Clean thinking tokens if returned
            return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

