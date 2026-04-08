from typing import List, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChunkSource(BaseModel):
    chunk_id: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    source_url: Optional[str] = None
    score: Optional[float] = None


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class QueryResponse(BaseModel):
    answer: str
    sources: List[ChunkSource]
    usage: TokenUsage
    latency_ms: float
