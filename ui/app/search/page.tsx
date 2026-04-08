"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  searchDocuments,
  semanticSearch,
  getFilterOptions,
} from "@/lib/api";
import type {
  SearchResult,
  SemanticSearchResult,
  FilterOptions,
} from "@/lib/types";
import SearchBar from "@/components/search/SearchBar";
import {
  FulltextResults,
  SemanticResults,
} from "@/components/search/SearchResults";
import Pagination from "@/components/documents/Pagination";

function SearchContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [mode, setMode] = useState<"fulltext" | "semantic">("fulltext");
  const [fulltextResults, setFulltextResults] = useState<SearchResult[]>([]);
  const [semanticResults, setSemanticResults] = useState<
    SemanticSearchResult[]
  >([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [filters, setFilters] = useState({
    platform: "",
    company: "",
    difficulty: "",
  });

  useEffect(() => {
    getFilterOptions()
      .then((res) => setOptions(res.data))
      .catch(() => {});
  }, []);

  const doSearch = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);

    try {
      if (mode === "fulltext") {
        const res = await searchDocuments({
          q: query,
          page,
          limit: 20,
          platform: filters.platform || undefined,
          company: filters.company || undefined,
          difficulty: filters.difficulty || undefined,
        });
        setFulltextResults(res.data);
        setTotal(res.meta.total);
      } else {
        const res = await semanticSearch({
          q: query,
          limit: 20,
          platform: filters.platform || undefined,
          company: filters.company || undefined,
          difficulty: filters.difficulty || undefined,
        });
        setSemanticResults(res.data);
        setTotal(res.meta.total);
      }
    } catch {
      setError("Search failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [query, mode, page, filters]);

  useEffect(() => {
    const q = searchParams.get("q");
    if (q) {
      setQuery(q);
    }
  }, [searchParams]);

  useEffect(() => {
    if (query.trim()) {
      doSearch();
    }
  }, [doSearch]);

  const handleSubmit = () => {
    if (query.trim()) {
      setPage(1);
      router.push(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <SearchBar
        query={query}
        onQueryChange={setQuery}
        onSubmit={handleSubmit}
        mode={mode}
        onModeChange={(m) => {
          setMode(m);
          setPage(1);
        }}
      />

      {options && (
        <div className="mt-4 flex flex-wrap gap-3">
          <select
            value={filters.platform}
            onChange={(e) => {
              setFilters((f) => ({ ...f, platform: e.target.value }));
              setPage(1);
            }}
            className="rounded border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-700"
          >
            <option value="">All Platforms</option>
            {options.platforms.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <select
            value={filters.company}
            onChange={(e) => {
              setFilters((f) => ({ ...f, company: e.target.value }));
              setPage(1);
            }}
            className="rounded border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-700"
          >
            <option value="">All Companies</option>
            {options.companies.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            value={filters.difficulty}
            onChange={(e) => {
              setFilters((f) => ({ ...f, difficulty: e.target.value }));
              setPage(1);
            }}
            className="rounded border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-700"
          >
            <option value="">All Difficulties</option>
            {options.difficulties.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
      )}

      {loading && <p className="mt-8 text-sm text-neutral-500">Searching...</p>}

      {error && <p className="mt-8 text-sm text-red-600">{error}</p>}

      {!loading && !error && query.trim() && (
        <>
          {mode === "fulltext" ? (
            <>
              <FulltextResults results={fulltextResults} />
              <Pagination
                page={page}
                total={total}
                limit={20}
                onChange={setPage}
              />
            </>
          ) : (
            <SemanticResults results={semanticResults} />
          )}
        </>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-6xl px-6 py-8">
          <p className="text-sm text-neutral-500">Loading...</p>
        </div>
      }
    >
      <SearchContent />
    </Suspense>
  );
}
