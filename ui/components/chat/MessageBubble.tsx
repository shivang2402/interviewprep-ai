import type { ChatMessage } from "@/lib/types";

interface MessageBubbleProps {
  message: ChatMessage;
}

interface ParsedSource {
  label: string;
  url: string;
}

function extractSources(text: string): { body: string; sources: ParsedSource[] } {
  // Split at **Sources** section
  const sourceSplit = text.split(/\*\*Sources\*\*/i);
  if (sourceSplit.length < 2) return { body: text, sources: [] };

  const body = sourceSplit[0].trimEnd();
  const sourcesBlock = sourceSplit[1];

  const sources: ParsedSource[] = [];
  const sourceRegex = /- \[(\d+)\]\s*(https?:\/\/[^\s]+)/g;
  let match;
  while ((match = sourceRegex.exec(sourcesBlock)) !== null) {
    sources.push({ label: match[1], url: match[2] });
  }

  return { body, sources };
}

function renderMarkdown(text: string) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];

  lines.forEach((line, i) => {
    // Bold text: **text**
    const parts: React.ReactNode[] = [];
    const boldRegex = /\*\*(.+?)\*\*/g;
    let lastIndex = 0;
    let boldMatch;

    while ((boldMatch = boldRegex.exec(line)) !== null) {
      if (boldMatch.index > lastIndex) {
        parts.push(line.slice(lastIndex, boldMatch.index));
      }
      parts.push(
        <strong key={`b-${i}-${boldMatch.index}`} className="font-semibold text-slate-900">
          {boldMatch[1]}
        </strong>
      );
      lastIndex = boldMatch.index + boldMatch[0].length;
    }
    if (lastIndex < line.length) {
      parts.push(line.slice(lastIndex));
    }

    // Inline URLs in the parts
    const rendered = parts.flatMap((part, pi) => {
      if (typeof part !== "string") return [part];
      const urlRegex = /(https?:\/\/[^\s)\]]+)/g;
      const urlParts = part.split(urlRegex);
      return urlParts.map((seg, si) =>
        urlRegex.test(seg) ? (
          <a
            key={`u-${i}-${pi}-${si}`}
            href={seg}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:text-indigo-800 underline underline-offset-2 break-all"
          >
            {seg}
          </a>
        ) : (
          <span key={`s-${i}-${pi}-${si}`}>{seg}</span>
        )
      );
    });

    // List items
    if (line.startsWith("- ")) {
      elements.push(
        <div key={i} className="flex gap-2 ml-1">
          <span className="text-indigo-400 mt-0.5 shrink-0">&#8226;</span>
          <span>{rendered.map((r, idx) => typeof r === "string" && idx === 0 ? (r as string).replace(/^- /, "") : r)}</span>
        </div>
      );
    } else if (line.trim() === "") {
      elements.push(<div key={i} className="h-2" />);
    } else {
      elements.push(<div key={i}>{rendered}</div>);
    }
  });

  return elements;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-md px-4 py-3 bg-indigo-600 text-white shadow-sm">
          <div className="text-sm whitespace-pre-wrap leading-relaxed">
            {message.content}
          </div>
          <div className="mt-1.5">
            <span className="text-[10px] text-indigo-200">
              {message.timestamp.toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        </div>
      </div>
    );
  }

  const { body, sources } = extractSources(message.content);

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] rounded-2xl rounded-bl-md px-5 py-4 bg-white border border-slate-200 text-slate-800 shadow-sm">
        <div className="text-sm leading-relaxed space-y-1">
          {renderMarkdown(body)}
        </div>

        {sources.length > 0 && (
          <div className="mt-4 pt-3 border-t border-slate-100">
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Sources
            </p>
            <div className="flex flex-wrap gap-2">
              {sources.map((src, i) => (
                <a
                  key={i}
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-50 border border-indigo-100 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 hover:border-indigo-200 transition-all hover:shadow-sm"
                >
                  <span className="w-4.5 h-4.5 rounded bg-indigo-200 text-indigo-700 text-[10px] font-bold flex items-center justify-center px-1">
                    {src.label}
                  </span>
                  <span className="truncate max-w-[200px]">
                    {src.url.replace(/^https?:\/\/(www\.)?/, "").split("/").slice(0, 2).join("/")}
                  </span>
                  <svg className="w-3 h-3 text-indigo-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center gap-2 mt-3">
          <span className="text-[10px] text-slate-400">
            {message.timestamp.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          {message.latency_ms && (
            <span className="text-[10px] text-slate-400 bg-slate-50 rounded px-1.5 py-0.5">
              {(message.latency_ms / 1000).toFixed(1)}s
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
