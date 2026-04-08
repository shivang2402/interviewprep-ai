import Link from "next/link";
import type { SearchResult, SemanticSearchResult, ParsedAs } from "@/lib/types";

function stripMarkdown(text: string): string {
  return text.replace(/\*\*(.*?)\*\*/g, "$1").replace(/\*(.*?)\*/g, "$1");
}

function ParsedAsBanner({ parsed }: { parsed?: ParsedAs }) {
  if (!parsed) return null;
  const parts: string[] = [];
  if (parsed.company) parts.push(parsed.company);
  if (parsed.role) parts.push(parsed.role);
  if (parsed.level) parts.push(`${parsed.level} level`);
  if (parts.length === 0) return null;

  return (
    <p className="mt-4 text-xs text-neutral-500">
      Showing results for:{" "}
      <span className="text-neutral-700 font-medium">
        {parts.join(" \u00B7 ")}
      </span>
      {parsed.query !== parts.join(" ") && parsed.query && (
        <span>
          {" \u00B7 "}&quot;{parsed.query}&quot;
        </span>
      )}
    </p>
  );
}

export function FulltextResults({
  results,
  parsedAs,
}: {
  results: SearchResult[];
  parsedAs?: ParsedAs;
}) {
  if (results.length === 0) {
    return (
      <>
        <ParsedAsBanner parsed={parsedAs} />
        <p className="text-sm text-neutral-500 mt-6">No results found.</p>
      </>
    );
  }

  return (
    <div className="mt-6 space-y-4">
      <ParsedAsBanner parsed={parsedAs} />
      {results.map((r) => (
        <Link
          key={r.document_id}
          href={`/documents/${r.document_id}`}
          className="block rounded border border-neutral-200 bg-white p-4 hover:border-neutral-300 transition-colors"
        >
          <h3 className="text-sm font-medium text-neutral-900">{r.title}</h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
            <span className="rounded bg-neutral-100 px-1.5 py-0.5">
              {r.source_platform}
            </span>
            {r.company && <span>{r.company}</span>}
            {r.role && <span>/ {r.role}</span>}
            {r.difficulty && <span>Difficulty: {r.difficulty}</span>}
            {r.interview_outcome && <span>Outcome: {r.interview_outcome}</span>}
          </div>
          {r.snippet && (
            <p className="mt-2 text-xs leading-relaxed text-neutral-600">
              {stripMarkdown(r.snippet)}
            </p>
          )}
        </Link>
      ))}
    </div>
  );
}

export function SemanticResults({
  results,
  parsedAs,
}: {
  results: SemanticSearchResult[];
  parsedAs?: ParsedAs;
}) {
  if (results.length === 0) {
    return (
      <>
        <ParsedAsBanner parsed={parsedAs} />
        <p className="text-sm text-neutral-500 mt-6">No results found.</p>
      </>
    );
  }

  return (
    <div className="mt-6 space-y-4">
      <ParsedAsBanner parsed={parsedAs} />
      {results.map((r) => (
        <Link
          key={r.chunk_id}
          href={`/documents/${r.document_id}`}
          className="block rounded border border-neutral-200 bg-white p-4 hover:border-neutral-300 transition-colors"
        >
          <div className="flex items-start justify-between gap-4">
            <h3 className="text-sm font-medium text-neutral-900">{r.title}</h3>
            <span className="shrink-0 text-xs text-neutral-400">
              {(r.similarity * 100).toFixed(1)}% match
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
            <span className="rounded bg-neutral-100 px-1.5 py-0.5">
              {r.source_platform}
            </span>
            {r.company && <span>{r.company}</span>}
            {r.role && <span>/ {r.role}</span>}
            {r.round_label && <span>Round: {r.round_label}</span>}
          </div>
          <p className="mt-2 text-xs leading-relaxed text-neutral-600 line-clamp-3">
            {r.raw_text}
          </p>
        </Link>
      ))}
    </div>
  );
}
