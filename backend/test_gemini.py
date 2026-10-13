import asyncio
from app.llm.gemini_client import gemini_client
from app.core.config import settings
import logging

logging.basicConfig(level=logging.DEBUG)

async def test():
    print(f"Using key: {settings.GEMINI_API_KEY[:5]}... and model: {settings.GEMINI_MODEL}")
    try:
        res = await gemini_client.generate('What medications am I on?')
        print('SUCCESS:', res)
    except Exception as e:
        print('ERROR:', repr(e))

asyncio.run(test())
