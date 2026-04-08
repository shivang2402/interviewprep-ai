import type { DocumentDetail as DocDetail } from "@/lib/types";

export default function DocumentDetailView({ doc }: { doc: DocDetail }) {
  return (
    <div>
      <h1 className="text-xl font-semibold text-neutral-900">{doc.title}</h1>

      <div className="mt-4 grid grid-cols-2 gap-x-8 gap-y-2 sm:grid-cols-3">
        <Field label="Platform" value={doc.source_platform} />
        <Field label="Company" value={doc.company} />
        <Field label="Role" value={doc.role} />
        <Field label="Experience Level" value={doc.experience_level} />
        <Field label="Difficulty" value={doc.difficulty} />
        <Field label="Outcome" value={doc.interview_outcome} />
        <Field label="Num Rounds" value={doc.num_rounds?.toString()} />
        <Field label="Interview Type" value={doc.interview_type} />
        <Field
          label="Published"
          value={
            doc.published_at
              ? new Date(doc.published_at).toLocaleDateString()
              : null
          }
        />
      </div>

      {doc.topics && doc.topics.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-neutral-500 uppercase">
            Topics
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {doc.topics.map((t) => (
              <span
                key={t}
                className="rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8">
        <h2 className="text-sm font-medium text-neutral-700 mb-3">Content</h2>
        <div className="rounded border border-neutral-200 bg-white p-6 text-sm leading-relaxed text-neutral-800 whitespace-pre-wrap">
          {doc.cleaned_content}
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (!value) return null;
  return (
    <div>
      <p className="text-xs font-medium text-neutral-500 uppercase">{label}</p>
      <p className="text-sm text-neutral-800">{value}</p>
    </div>
  );
}
