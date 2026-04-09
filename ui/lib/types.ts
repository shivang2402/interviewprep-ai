export interface ChatSource {
  chunk_id: string | null;
  company: string | null;
  role: string | null;
  source_url: string | null;
  score: number | null;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
  usage: TokenUsage;
  latency_ms: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: ChatSource[];
  latency_ms?: number;
  timestamp: Date;
}
