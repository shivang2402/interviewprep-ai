"use client";

import { useEffect, useState } from "react";
import {
  getStatsOverview,
  getStatsCompanies,
  getStatsTopics,
  getStatsOutcomes,
} from "@/lib/api";
import type {
  StatsOverview,
  CompanyStat,
  TopicStat,
  OutcomeStat,
} from "@/lib/types";
import StatCard from "@/components/stats/StatCard";
import CompanyTable from "@/components/stats/CompanyTable";
import TopicsChart from "@/components/stats/TopicsChart";
import OutcomeChart from "@/components/stats/OutcomeChart";

export default function StatsPage() {
  const [overview, setOverview] = useState<StatsOverview | null>(null);
  const [companies, setCompanies] = useState<CompanyStat[]>([]);
  const [topics, setTopics] = useState<TopicStat[]>([]);
  const [outcomes, setOutcomes] = useState<OutcomeStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getStatsOverview(),
      getStatsCompanies(),
      getStatsTopics(),
      getStatsOutcomes(),
    ])
      .then(([ov, co, to, ou]) => {
        setOverview(ov.data);
        setCompanies(co.data);
        setTopics(to.data);
        setOutcomes(ou.data);
      })
      .catch(() => setError("Failed to load statistics."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-8">
        <p className="text-sm text-neutral-500">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-8">
        <p className="text-sm text-red-600">{error}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="text-xl font-semibold text-neutral-900">Statistics</h1>

      {overview && (
        <>
          <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard
              label="Total Documents"
              value={overview.total_documents}
            />
            <StatCard label="Companies" value={overview.total_companies} />
            <StatCard label="Roles" value={overview.total_roles} />
            <StatCard
              label="Platforms"
              value={overview.platform_breakdown.length}
            />
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
            {overview.platform_breakdown.map((p) => (
              <StatCard
                key={p.platform}
                label={p.platform}
                value={p.count}
              />
            ))}
          </div>
        </>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="text-sm font-medium text-neutral-700 mb-3">
            Top Companies
          </h2>
          <CompanyTable companies={companies.slice(0, 25)} />
        </div>

        <div className="space-y-6">
          <TopicsChart topics={topics} />
          <OutcomeChart outcomes={outcomes} />
        </div>
      </div>
    </div>
  );
}
