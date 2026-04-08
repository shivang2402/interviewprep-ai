interface StatCardProps {
  label: string;
  value: string | number;
}

export default function StatCard({ label, value }: StatCardProps) {
  return (
    <div className="rounded border border-neutral-200 bg-white p-5">
      <p className="text-2xl font-semibold text-neutral-900">
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
      <p className="mt-1 text-sm text-neutral-500">{label}</p>
    </div>
  );
}
