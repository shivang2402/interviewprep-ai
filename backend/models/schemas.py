from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class PaginationMeta(BaseModel):
    total: int
    page: int
    limit: int


class PaginatedResponse(BaseModel):
    data: List[Any]
    meta: PaginationMeta


class SingleResponse(BaseModel):
    data: Any


class DocumentSummary(BaseModel):
    document_id: str
    source_platform: str
    source_url: str
    title: str
    word_count: int
    published_at: Optional[str] = None
    scraped_at: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    experience_level: Optional[str] = None
    interview_outcome: Optional[str] = None
    difficulty: Optional[str] = None
    interview_type: Optional[str] = None
    topics: Optional[List[str]] = None
    num_rounds: Optional[int] = None


class DocumentDetail(DocumentSummary):
    content_hash: Optional[str] = None
    cleaned_content: str
    processed_at: Optional[str] = None
    scrape_batch_id: Optional[str] = None
    source_metadata: Optional[Dict] = None


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    total_chunks: int
    chunk_text: str
    raw_text: str
    word_count: int
    char_start_offset: int
    char_end_offset: int
    strategy: str
    round_label: Optional[str] = None


class SearchResult(BaseModel):
    document_id: str
    source_platform: str
    title: str
    word_count: int
    published_at: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    difficulty: Optional[str] = None
    interview_outcome: Optional[str] = None
    rank: Optional[float] = None
    snippet: Optional[str] = None


class SemanticSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    raw_text: str
    chunk_index: int
    total_chunks: int
    round_label: Optional[str] = None
    word_count: int
    title: str
    source_platform: str
    company: Optional[str] = None
    role: Optional[str] = None
    difficulty: Optional[str] = None
    interview_outcome: Optional[str] = None
    similarity: float


class StatsOverview(BaseModel):
    total_documents: int
    total_companies: int
    total_roles: int
    platform_breakdown: List[Dict]


class CompanyStat(BaseModel):
    company: str
    document_count: int


class TopicStat(BaseModel):
    topic: str
    frequency: int


class OutcomeStat(BaseModel):
    outcome: str
    count: int


class FilterOptions(BaseModel):
    platforms: List[str]
    companies: List[str]
    roles: List[str]
    difficulties: List[str]
    outcomes: List[str]
