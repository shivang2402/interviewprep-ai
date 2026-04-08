"use client";

interface SearchBarProps {
  query: string;
  onQueryChange: (q: string) => void;
  onSubmit: () => void;
  mode: "fulltext" | "semantic";
  onModeChange: (mode: "fulltext" | "semantic") => void;
}

export default function SearchBar({
  query,
  onQueryChange,
  onSubmit,
  mode,
  onModeChange,
}: SearchBarProps) {
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit();
  };

  return (
    <div>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Search interview experiences..."
          className="flex-1 rounded border border-neutral-300 px-4 py-2.5 text-sm text-neutral-900 placeholder-neutral-400 focus:border-neutral-500 focus:outline-none"
        />
        <button
          type="submit"
          className="rounded bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-800"
        >
          Search
        </button>
      </form>
      <div className="mt-3 flex gap-4">
        <label className="flex items-center gap-1.5 text-sm text-neutral-600 cursor-pointer">
          <input
            type="radio"
            name="searchMode"
            checked={mode === "fulltext"}
            onChange={() => onModeChange("fulltext")}
            className="accent-neutral-900"
          />
          Full-text search
        </label>
        <label className="flex items-center gap-1.5 text-sm text-neutral-600 cursor-pointer">
          <input
            type="radio"
            name="searchMode"
            checked={mode === "semantic"}
            onChange={() => onModeChange("semantic")}
            className="accent-neutral-900"
          />
          Semantic search
        </label>
      </div>
    </div>
  );
}
