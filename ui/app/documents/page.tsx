"use client";

import { useEffect, useState, useCallback } from "react";
import { getDocuments, getFilterOptions } from "@/lib/api";
import type { DocumentSummary, FilterOptions } from "@/lib/types";
import DocumentCard from "@/components/documents/DocumentCard";
import FilterBar from "@/components/documents/FilterBar";
import Pagination from "@/components/documents/Pagination";

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    platform: "",
    company: "",
    role: "",
    difficulty: "",
    outcome: "",
  });

  const limit = 20;

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getDocuments({
        page,
        limit,
        platform: filters.platform || undefined,
        company: filters.company || undefined,
        role: filters.role || undefined,
        difficulty: filters.difficulty || undefined,
        outcome: filters.outcome || undefined,
      });
      setDocs(res.data);
      setTotal(res.meta.total);
    } catch {
      setError("Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, [page, filters]);

  useEffect(() => {
    getFilterOptions()
      .then((res) => setOptions(res.data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  const handleFilterChange = (key: string, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="text-xl font-semibold text-neutral-900">Documents</h1>
      <p className="mt-1 text-sm text-neutral-500">
        {total.toLocaleString()} interview experiences
      </p>

      {options && (
        <div className="mt-5">
          <FilterBar
            options={options}
            filters={filters}
            onChange={handleFilterChange}
          />
        </div>
      )}

      {loading && (
        <p className="mt-8 text-sm text-neutral-500">Loading...</p>
      )}

      {error && (
        <p className="mt-8 text-sm text-red-600">{error}</p>
      )}

      {!loading && !error && (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {docs.map((doc) => (
              <DocumentCard key={doc.document_id} doc={doc} />
            ))}
          </div>

          {docs.length === 0 && (
            <p className="mt-8 text-sm text-neutral-500">
              No documents match the selected filters.
            </p>
          )}

          <Pagination
            page={page}
            total={total}
            limit={limit}
            onChange={setPage}
          />
        </>
      )}
    </div>
  );
}
