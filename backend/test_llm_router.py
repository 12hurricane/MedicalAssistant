import pytest
from unittest.mock import AsyncMock, patch
from app.llm.client import get_generative_response, llm_router, LLMUnavailable
from app.llm.ollama_client import LLMUnavailable as OllamaUnavailable
from app.llm.gemini_client import LLMUnavailable as GeminiUnavailable

@pytest.mark.asyncio
async def test_groq_used_first_when_available():
    with patch("app.llm.client.groq_client") as mock_groq, \
         patch("app.llm.client.hf_client") as mock_hf, \
         patch("app.llm.client.gemini_client") as mock_gemini, \
         patch("app.llm.client.ollama_client") as mock_ollama:
        mock_groq.is_available = AsyncMock(return_value=True)
        mock_groq.generate_response = AsyncMock(return_value='{"trend":"STABLE"}')

        result, provider = await get_generative_response("test prompt", timeout=10.0)

        assert provider == "GENERATED_GROQ"
        assert result == '{"trend":"STABLE"}'
        mock_hf.generate_response.assert_not_called()
        mock_gemini.generate.assert_not_called()
        mock_ollama.generate.assert_not_called()

@pytest.mark.asyncio
async def test_hf_fallback_when_groq_fails():
    with patch("app.llm.client.groq_client") as mock_groq, \
         patch("app.llm.client.hf_client") as mock_hf, \
         patch("app.llm.client.gemini_client") as mock_gemini, \
         patch("app.llm.client.ollama_client") as mock_ollama:
        mock_groq.is_available = AsyncMock(return_value=True)
        mock_groq.generate_response = AsyncMock(side_effect=RuntimeError("Groq 429 rate limit"))
        mock_hf.generate_response = AsyncMock(return_value="HF response text")

        result, provider = await get_generative_response("test prompt", timeout=10.0)

        assert provider == "GENERATED_HF"
        assert result == "HF response text"
        mock_gemini.generate.assert_not_called()
        mock_ollama.generate.assert_not_called()

@pytest.mark.asyncio
async def test_gemini_fallback_when_groq_and_hf_fail():
    with patch("app.llm.client.groq_client") as mock_groq, \
         patch("app.llm.client.hf_client") as mock_hf, \
         patch("app.llm.client.gemini_client") as mock_gemini, \
         patch("app.llm.client.ollama_client") as mock_ollama:
        mock_groq.is_available = AsyncMock(return_value=True)
        mock_groq.generate_response = AsyncMock(side_effect=RuntimeError("Groq error"))
        mock_hf.generate_response = AsyncMock(side_effect=RuntimeError("HF 402 no credits"))
        mock_gemini.is_available = AsyncMock(return_value=True)
        mock_gemini.generate = AsyncMock(return_value="Gemini response")

        result, provider = await get_generative_response("test prompt", timeout=10.0)

        assert provider == "GENERATED_GEMINI"
        assert result == "Gemini response"
        mock_ollama.generate.assert_not_called()

@pytest.mark.asyncio
async def test_ollama_fallback_when_groq_hf_and_gemini_fail():
    with patch("app.llm.client.groq_client") as mock_groq, \
         patch("app.llm.client.hf_client") as mock_hf, \
         patch("app.llm.client.gemini_client") as mock_gemini, \
         patch("app.llm.client.ollama_client") as mock_ollama:
        mock_groq.is_available = AsyncMock(return_value=False)
        mock_hf.generate_response = AsyncMock(side_effect=RuntimeError("HF down"))
        mock_gemini.is_available = AsyncMock(return_value=False)
        mock_ollama.is_available = AsyncMock(return_value=True)
        mock_ollama.generate = AsyncMock(return_value="Ollama offline safety response")

        result, provider = await get_generative_response("test prompt", timeout=10.0)

        assert provider == "GENERATED_OLLAMA"
        assert result == "Ollama offline safety response"

@pytest.mark.asyncio
async def test_llm_unavailable_when_all_tiers_fail():
    with patch("app.llm.client.groq_client") as mock_groq, \
         patch("app.llm.client.hf_client") as mock_hf, \
         patch("app.llm.client.gemini_client") as mock_gemini, \
         patch("app.llm.client.ollama_client") as mock_ollama:
        mock_groq.is_available = AsyncMock(return_value=True)
        mock_groq.generate_response = AsyncMock(side_effect=RuntimeError("Groq down"))
        mock_hf.generate_response = AsyncMock(side_effect=RuntimeError("HF down"))
        mock_gemini.is_available = AsyncMock(return_value=True)
        mock_gemini.generate = AsyncMock(side_effect=GeminiUnavailable("Gemini down"))
        mock_ollama.is_available = AsyncMock(return_value=True)
        mock_ollama.generate = AsyncMock(side_effect=OllamaUnavailable("Ollama down"))

        with pytest.raises(LLMUnavailable):
            await get_generative_response("test prompt", timeout=10.0)

@pytest.mark.asyncio
async def test_llm_router_class_priority_flow():
    with patch.object(llm_router, "groq_client") as mock_groq, \
         patch.object(llm_router, "hf_client") as mock_hf, \
         patch.object(llm_router, "ollama_client") as mock_ollama:
        # Tier 1: Groq fast path
        mock_groq.is_available = AsyncMock(return_value=True)
        mock_groq.generate_response = AsyncMock(return_value="Fast LPU")
        res = await llm_router.generate_response([{"role": "user", "content": "hi"}])
        assert res == "Fast LPU"
        mock_hf.generate_response.assert_not_called()

        # Tier 2: Groq fails -> HF called
        mock_groq.generate_response = AsyncMock(side_effect=RuntimeError("LPU rate limit"))
        mock_hf.token = "hf_token"
        mock_hf.generate_response = AsyncMock(return_value="HF text")
        res2 = await llm_router.generate_response([{"role": "user", "content": "hi"}])
        assert res2 == "HF text"
