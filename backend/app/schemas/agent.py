from pydantic import BaseModel, Field

class AgentChatRequest(BaseModel):
    message: str = Field(..., description="The patient's message to the AI agent.")

class AgentChatResponse(BaseModel):
    response: str = Field(..., description="The AI agent's response text.")
