import type { CompanyStat } from "@/lib/types";

export default function CompanyTable({
  companies,
}: {
  companies: CompanyStat[];
}) {
  return (
    <div className="rounded border border-neutral-200 bg-white overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-200 bg-neutral-50">
            <th className="px-4 py-2.5 text-left font-medium text-neutral-600">
              Company
            </th>
            <th className="px-4 py-2.5 text-right font-medium text-neutral-600">
              Documents
            </th>
          </tr>
        </thead>
        <tbody>
          {companies.map((c) => (
            <tr
              key={c.company}
              className="border-b border-neutral-100 last:border-0"
            >
              <td className="px-4 py-2 text-neutral-800">{c.company}</td>
              <td className="px-4 py-2 text-right text-neutral-600">
                {c.document_count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
