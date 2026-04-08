import Link from "next/link";
import type { DocumentSummary } from "@/lib/types";

const PLATFORM_STYLES: Record<string, string> = {
  gfg: "bg-neutral-100 text-neutral-700",
  leetcode: "bg-neutral-200 text-neutral-800",
  medium: "bg-neutral-300 text-neutral-900",
};

export default function DocumentCard({ doc }: { doc: DocumentSummary }) {
  return (
    <Link
      href={`/documents/${doc.document_id}`}
      className="block rounded border border-neutral-200 bg-white p-5 hover:border-neutral-300 transition-colors"
    >
      <h3 className="text-sm font-medium text-neutral-900 line-clamp-2">
        {doc.title}
      </h3>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span
          className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
            PLATFORM_STYLES[doc.source_platform] || "bg-neutral-100 text-neutral-600"
          }`}
        >
          {doc.source_platform}
        </span>
        {doc.company && (
          <span className="text-xs text-neutral-500">{doc.company}</span>
        )}
        {doc.role && (
          <span className="text-xs text-neutral-400">/ {doc.role}</span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-neutral-400">
        {doc.difficulty && <span>Difficulty: {doc.difficulty}</span>}
        {doc.interview_outcome && <span>Outcome: {doc.interview_outcome}</span>}
        {doc.published_at && (
          <span>{new Date(doc.published_at).toLocaleDateString()}</span>
        )}
      </div>
    </Link>
  );
}
