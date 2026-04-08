export interface PaginationMeta {
  total: number;
  page: number;
  limit: number;
}

export interface ParsedAs {
  company?: string;
  role?: string;
  level?: string;
  query: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  meta: PaginationMeta;
  parsed_as?: ParsedAs;
}

export interface SingleResponse<T> {
  data: T;
}

export interface DocumentSummary {
  document_id: string;
  source_platform: string;
  source_url: string;
  title: string;
  word_count: number;
  published_at: string | null;
  scraped_at: string | null;
  company: string | null;
  role: string | null;
  experience_level: string | null;
  interview_outcome: string | null;
  difficulty: string | null;
  interview_type: string | null;
  topics: string[] | null;
  num_rounds: number | null;
}

export interface DocumentDetail extends DocumentSummary {
  content_hash: string | null;
  cleaned_content: string;
  processed_at: string | null;
  scrape_batch_id: string | null;
  source_metadata: Record<string, unknown> | null;
}

export interface DocumentChunk {
  chunk_id: string;
  document_id: string;
  chunk_index: number;
  total_chunks: number;
  chunk_text: string;
  raw_text: string;
  word_count: number;
  char_start_offset: number;
  char_end_offset: number;
  strategy: string;
  round_label: string | null;
}

export interface SearchResult {
  document_id: string;
  source_platform: string;
  title: string;
  word_count: number;
  published_at: string | null;
  company: string | null;
  role: string | null;
  difficulty: string | null;
  interview_outcome: string | null;
  rank: number | null;
  snippet: string | null;
}

export interface SemanticSearchResult {
  chunk_id: string;
  document_id: string;
  raw_text: string;
  chunk_index: number;
  total_chunks: number;
  round_label: string | null;
  word_count: number;
  title: string;
  source_platform: string;
  company: string | null;
  role: string | null;
  difficulty: string | null;
  interview_outcome: string | null;
  similarity: number;
}

export interface StatsOverview {
  total_documents: number;
  total_companies: number;
  total_roles: number;
  platform_breakdown: { platform: string; count: number }[];
}

export interface CompanyStat {
  company: string;
  document_count: number;
}

export interface TopicStat {
  topic: string;
  frequency: number;
}

export interface OutcomeStat {
  outcome: string;
  count: number;
}

export interface FilterOptions {
  platforms: string[];
  companies: string[];
  roles: string[];
  difficulties: string[];
  outcomes: string[];
}
