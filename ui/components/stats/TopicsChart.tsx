import type { TopicStat } from "@/lib/types";

export default function TopicsChart({ topics }: { topics: TopicStat[] }) {
  if (topics.length === 0) return null;
  const max = topics[0]?.frequency || 1;

  return (
    <div className="rounded border border-neutral-200 bg-white p-5">
      <h3 className="text-sm font-medium text-neutral-700 mb-4">
        Top Topics
      </h3>
      <div className="space-y-2.5">
        {topics.slice(0, 20).map((t) => (
          <div key={t.topic} className="flex items-center gap-3">
            <span className="w-32 shrink-0 text-xs text-neutral-600 truncate">
              {t.topic}
            </span>
            <div className="flex-1 h-4 bg-neutral-100 rounded overflow-hidden">
              <div
                className="h-full bg-neutral-400 rounded"
                style={{ width: `${(t.frequency / max) * 100}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-xs text-neutral-500 text-right">
              {t.frequency}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
