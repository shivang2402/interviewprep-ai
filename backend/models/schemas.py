from typing import List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChatSource(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    source_url: Optional[str] = None


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    answer: str
    sources: List[ChatSource]
    usage: TokenUsage
