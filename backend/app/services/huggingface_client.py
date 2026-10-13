import os
import re
import logging
import httpx
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)
load_dotenv()

class HuggingFaceClient:
    """Async client for Hugging Face Chat Completions API."""

    def __init__(
        self,
        token: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0
    ):
        self.token = token or os.getenv("HF_TOKEN")
        self.model = model or os.getenv("HF_AGENT_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
        self.timeout = timeout
        self.endpoint = "https://router.huggingface.co/v1/chat/completions"

    def _strip_thinking_tags(self, text: str) -> str:
        """Removes internal reasoning blocks <think>...</think> from output."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 800
    ) -> str:
        token = self.token or os.getenv("HF_TOKEN")
        if not token or token == "hf_your_actual_token_here":
            raise ValueError("HF_TOKEN is not configured in backend environment.")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.endpoint, headers=headers, json=payload)
            
            if response.status_code != 200:
                logger.error(f"Hugging Face API returned {response.status_code}: {response.text}")
                response.raise_for_status()

            data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            return self._strip_thinking_tags(raw_content)
