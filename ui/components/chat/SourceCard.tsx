import type { ChatSource } from "@/lib/types";

interface SourceCardProps {
  sources: ChatSource[];
}

export default function SourceCard({ sources }: SourceCardProps) {
  const unique = sources.filter(
    (s, i, arr) =>
      arr.findIndex(
        (o) => o.source_url === s.source_url && o.company === s.company
      ) === i
  );

  if (unique.length === 0) return null;

  return (
    <div className="mt-3 border-t border-neutral-200 pt-3">
      <p className="text-xs font-medium text-neutral-500 mb-2">
        Sources ({unique.length})
      </p>
      <div className="flex flex-wrap gap-2">
        {unique.map((source, i) => (
          <a
            key={i}
            href={source.source_url || "#"}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md bg-neutral-100 px-2.5 py-1 text-xs text-neutral-700 hover:bg-neutral-200 transition-colors"
          >
            {source.company && (
              <span className="font-medium">{source.company}</span>
            )}
            {source.company && source.role && (
              <span className="text-neutral-400">&middot;</span>
            )}
            {source.role && <span>{source.role}</span>}
            {!source.company && !source.role && (
              <span>Source {i + 1}</span>
            )}
          </a>
        ))}
      </div>
    </div>
  );
}
