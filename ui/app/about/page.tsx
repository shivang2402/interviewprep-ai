import Image from "next/image";

export default function AboutPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      <div className="flex flex-col items-center mb-10">
        <Image
          src="/logo.png"
          alt="InterviewPrep AI Logo"
          width={180}
          height={180}
          className="mb-6"
        />
        <h1 className="text-3xl font-bold text-slate-900 mb-2">
          InterviewPrep AI
        </h1>
        <p className="text-lg text-slate-500">
          Your Intelligent Interview Coach
        </p>
      </div>

      <div className="space-y-8 text-slate-700 leading-relaxed">
        <section>
          <h2 className="text-xl font-semibold text-slate-900 mb-3">
            What is InterviewPrep AI?
          </h2>
          <p>
            InterviewPrep AI is an AI-powered interview preparation assistant
            that helps you get ready for technical interviews. It uses a
            Retrieval-Augmented Generation (RAG) pipeline to provide accurate,
            context-aware answers based on real interview experiences and
            technical knowledge.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-900 mb-3">
            How It Works
          </h2>
          <ul className="space-y-2">
            <li className="flex gap-2">
              <span className="text-indigo-500 font-bold shrink-0">1.</span>
              <span>
                Ask any interview-related question — behavioral, technical, or
                company-specific.
              </span>
            </li>
            <li className="flex gap-2">
              <span className="text-indigo-500 font-bold shrink-0">2.</span>
              <span>
                Our RAG pipeline retrieves the most relevant interview
                experiences and knowledge from our curated corpus.
              </span>
            </li>
            <li className="flex gap-2">
              <span className="text-indigo-500 font-bold shrink-0">3.</span>
              <span>
                An LLM generates a tailored answer grounded in real data, with
                sources linked for transparency.
              </span>
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-900 mb-3">
            Key Features
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 mb-1">
                RAG-Powered Answers
              </h3>
              <p className="text-sm text-slate-500">
                Answers grounded in real interview experiences, not just generic
                advice.
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 mb-1">
                Source Transparency
              </h3>
              <p className="text-sm text-slate-500">
                Every answer includes links to the original sources so you can
                verify and explore further.
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 mb-1">
                Company-Specific Prep
              </h3>
              <p className="text-sm text-slate-500">
                Get insights tailored to specific companies and roles from real
                interview reports.
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-900 mb-1">
                Continuous Updates
              </h3>
              <p className="text-sm text-slate-500">
                Our corpus is regularly refreshed with new interview experiences
                via automated pipelines.
              </p>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-slate-900 mb-3">
            Tech Stack
          </h2>
          <div className="flex flex-wrap gap-2">
            {[
              "Next.js",
              "FastAPI",
              "PostgreSQL + pgvector",
              "sentence-transformers",
              "OpenAI",
              "Apache Airflow",
              "MLflow",
              "Google Cloud Platform",
              "Docker",
              "Terraform",
              "GitHub Actions",
            ].map((tech) => (
              <span
                key={tech}
                className="rounded-full bg-indigo-50 border border-indigo-100 px-3 py-1 text-xs font-medium text-indigo-700"
              >
                {tech}
              </span>
            ))}
          </div>
        </section>

        <section className="border-t border-slate-200 pt-6">
          <p className="text-sm text-slate-400 text-center">
            Built as part of the MLOps course project at Northeastern University.
          </p>
        </section>
      </div>
    </div>
  );
}
