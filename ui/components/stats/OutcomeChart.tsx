import type { OutcomeStat } from "@/lib/types";

export default function OutcomeChart({
  outcomes,
}: {
  outcomes: OutcomeStat[];
}) {
  const total = outcomes.reduce((sum, o) => sum + o.count, 0) || 1;

  return (
    <div className="rounded border border-neutral-200 bg-white p-5">
      <h3 className="text-sm font-medium text-neutral-700 mb-4">
        Outcome Distribution
      </h3>
      <div className="space-y-3">
        {outcomes.map((o) => {
          const pct = ((o.count / total) * 100).toFixed(1);
          return (
            <div key={o.outcome}>
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-neutral-700">{o.outcome}</span>
                <span className="text-neutral-500">
                  {o.count} ({pct}%)
                </span>
              </div>
              <div className="h-3 bg-neutral-100 rounded overflow-hidden">
                <div
                  className="h-full bg-neutral-500 rounded"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
