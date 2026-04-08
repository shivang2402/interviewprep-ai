"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getDocument, getDocumentChunks } from "@/lib/api";
import type {
  DocumentDetail,
  DocumentChunk,
} from "@/lib/types";
import DocumentDetailView from "@/components/documents/DocumentDetail";

export default function DocumentDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [showChunks, setShowChunks] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([getDocument(id), getDocumentChunks(id)])
      .then(([docRes, chunkRes]) => {
        setDoc(docRes.data);
        setChunks(chunkRes.data);
      })
      .catch(() => setError("Failed to load document."))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <p className="text-sm text-neutral-500">Loading...</p>
      </div>
    );
  }

  if (error || !doc) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <p className="text-sm text-red-600">{error || "Document not found."}</p>
        <Link
          href="/documents"
          className="mt-4 inline-block text-sm text-neutral-500 hover:text-neutral-700"
        >
          Back to documents
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <Link
        href="/documents"
        className="text-sm text-neutral-500 hover:text-neutral-700"
      >
        Back to documents
      </Link>

      <div className="mt-4">
        <DocumentDetailView doc={doc} />
      </div>

      {chunks.length > 0 && (
        <div className="mt-8">
          <button
            onClick={() => setShowChunks(!showChunks)}
            className="text-sm font-medium text-neutral-700 hover:text-neutral-900"
          >
            {showChunks ? "Hide" : "Show"} Chunks ({chunks.length})
          </button>

          {showChunks && (
            <div className="mt-4 space-y-3">
              {chunks.map((chunk) => (
                <div
                  key={chunk.chunk_id}
                  className="rounded border border-neutral-200 bg-white p-4"
                >
                  <div className="flex items-center gap-3 text-xs text-neutral-500 mb-2">
                    <span>
                      Chunk {chunk.chunk_index + 1} of {chunk.total_chunks}
                    </span>
                    <span>{chunk.strategy}</span>
                    {chunk.round_label && (
                      <span>Round: {chunk.round_label}</span>
                    )}
                    <span>{chunk.word_count} words</span>
                  </div>
                  <p className="text-sm text-neutral-700 whitespace-pre-wrap">
                    {chunk.raw_text}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
