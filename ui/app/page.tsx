"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getStatsOverview } from "@/lib/api";
import type { StatsOverview } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [stats, setStats] = useState<StatsOverview | null>(null);

  useEffect(() => {
    getStatsOverview()
      .then((res) => setStats(res.data))
      .catch(() => {});
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-neutral-900">
          InterviewPrep AI
        </h1>
        <p className="mt-3 text-neutral-500">
          A searchable database of real software engineering interview
          experiences
        </p>
      </div>

      <form onSubmit={handleSearch} className="mx-auto mt-10 max-w-xl">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search interview experiences..."
            className="flex-1 rounded border border-neutral-300 px-4 py-2.5 text-sm text-neutral-900 placeholder-neutral-400 focus:border-neutral-500 focus:outline-none"
          />
          <button
            type="submit"
            className="rounded bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-800"
          >
            Search
          </button>
        </div>
      </form>

      {stats && (
        <div className="mx-auto mt-12 grid max-w-2xl grid-cols-3 gap-6">
          <div className="rounded border border-neutral-200 bg-white p-5 text-center">
            <p className="text-2xl font-semibold text-neutral-900">
              {stats.total_documents.toLocaleString()}
            </p>
            <p className="mt-1 text-sm text-neutral-500">Documents</p>
          </div>
          <div className="rounded border border-neutral-200 bg-white p-5 text-center">
            <p className="text-2xl font-semibold text-neutral-900">
              {stats.total_companies.toLocaleString()}
            </p>
            <p className="mt-1 text-sm text-neutral-500">Companies</p>
          </div>
          <div className="rounded border border-neutral-200 bg-white p-5 text-center">
            <p className="text-2xl font-semibold text-neutral-900">
              {stats.platform_breakdown.length}
            </p>
            <p className="mt-1 text-sm text-neutral-500">Platforms</p>
          </div>
        </div>
      )}

      <div className="mx-auto mt-12 max-w-2xl text-center">
        <p className="text-sm leading-relaxed text-neutral-500">
          This project scrapes interview experiences from GeeksforGeeks,
          LeetCode, and Medium, processes them through a multi-step pipeline,
          and makes them searchable with full-text and semantic search powered by
          pgvector embeddings.
        </p>
        <div className="mt-6 flex justify-center gap-4">
          <Link
            href="/documents"
            className="rounded border border-neutral-300 px-4 py-2 text-sm text-neutral-700 hover:bg-neutral-50"
          >
            Browse Documents
          </Link>
          <Link
            href="/stats"
            className="rounded border border-neutral-300 px-4 py-2 text-sm text-neutral-700 hover:bg-neutral-50"
          >
            View Statistics
          </Link>
        </div>
      </div>
    </div>
  );
}
