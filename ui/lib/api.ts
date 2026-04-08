import type {
  PaginatedResponse,
  SingleResponse,
  DocumentSummary,
  DocumentDetail,
  DocumentChunk,
  SearchResult,
  SemanticSearchResult,
  StatsOverview,
  CompanyStat,
  TopicStat,
  OutcomeStat,
  FilterOptions,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

export async function getDocuments(params: {
  page?: number;
  limit?: number;
  platform?: string;
  company?: string;
  role?: string;
  outcome?: string;
  difficulty?: string;
}): Promise<PaginatedResponse<DocumentSummary>> {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.limit) query.set("limit", String(params.limit));
  if (params.platform) query.set("platform", params.platform);
  if (params.company) query.set("company", params.company);
  if (params.role) query.set("role", params.role);
  if (params.outcome) query.set("outcome", params.outcome);
  if (params.difficulty) query.set("difficulty", params.difficulty);
  return apiFetch(`/api/documents?${query.toString()}`);
}

export async function getDocument(
  id: string
): Promise<SingleResponse<DocumentDetail>> {
  return apiFetch(`/api/documents/${id}`);
}

export async function getDocumentChunks(
  id: string
): Promise<PaginatedResponse<DocumentChunk>> {
  return apiFetch(`/api/documents/${id}/chunks`);
}

export async function searchDocuments(params: {
  q: string;
  page?: number;
  limit?: number;
  platform?: string;
  company?: string;
  difficulty?: string;
}): Promise<PaginatedResponse<SearchResult>> {
  const query = new URLSearchParams();
  query.set("q", params.q);
  if (params.page) query.set("page", String(params.page));
  if (params.limit) query.set("limit", String(params.limit));
  if (params.platform) query.set("platform", params.platform);
  if (params.company) query.set("company", params.company);
  if (params.difficulty) query.set("difficulty", params.difficulty);
  return apiFetch(`/api/search?${query.toString()}`);
}

export async function semanticSearch(params: {
  q: string;
  limit?: number;
  platform?: string;
  company?: string;
  difficulty?: string;
}): Promise<PaginatedResponse<SemanticSearchResult>> {
  const query = new URLSearchParams();
  query.set("q", params.q);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.platform) query.set("platform", params.platform);
  if (params.company) query.set("company", params.company);
  if (params.difficulty) query.set("difficulty", params.difficulty);
  return apiFetch(`/api/search/semantic?${query.toString()}`);
}

export async function getStatsOverview(): Promise<
  SingleResponse<StatsOverview>
> {
  return apiFetch("/api/stats/overview");
}

export async function getStatsCompanies(): Promise<
  PaginatedResponse<CompanyStat>
> {
  return apiFetch("/api/stats/companies");
}

export async function getStatsTopics(): Promise<
  PaginatedResponse<TopicStat>
> {
  return apiFetch("/api/stats/topics");
}

export async function getStatsOutcomes(): Promise<
  PaginatedResponse<OutcomeStat>
> {
  return apiFetch("/api/stats/outcomes");
}

export async function getFilterOptions(): Promise<
  SingleResponse<FilterOptions>
> {
  return apiFetch("/api/filters/options");
}
