"use client";

import type { FilterOptions } from "@/lib/types";

interface FilterBarProps {
  options: FilterOptions;
  filters: {
    platform: string;
    company: string;
    role: string;
    difficulty: string;
    outcome: string;
  };
  onChange: (key: string, value: string) => void;
}

export default function FilterBar({ options, filters, onChange }: FilterBarProps) {
  return (
    <div className="flex flex-wrap gap-3">
      <select
        value={filters.platform}
        onChange={(e) => onChange("platform", e.target.value)}
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
        onChange={(e) => onChange("company", e.target.value)}
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
        value={filters.role}
        onChange={(e) => onChange("role", e.target.value)}
        className="rounded border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-700"
      >
        <option value="">All Roles</option>
        {options.roles.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>

      <select
        value={filters.difficulty}
        onChange={(e) => onChange("difficulty", e.target.value)}
        className="rounded border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-700"
      >
        <option value="">All Difficulties</option>
        {options.difficulties.map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </select>

      <select
        value={filters.outcome}
        onChange={(e) => onChange("outcome", e.target.value)}
        className="rounded border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-700"
      >
        <option value="">All Outcomes</option>
        {options.outcomes.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
