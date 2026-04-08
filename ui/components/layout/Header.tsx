import Link from "next/link";

export default function Header() {
  return (
    <header className="border-b border-neutral-200 bg-white">
      <div className="mx-auto flex max-w-3xl items-center px-6 py-4">
        <Link href="/" className="text-lg font-semibold text-neutral-900">
          InterviewPrep AI
        </Link>
        <span className="ml-3 rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs text-neutral-500">
          Chat
        </span>
      </div>
    </header>
  );
}
