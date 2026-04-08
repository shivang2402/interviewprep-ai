import type { ChatMessage } from "@/lib/types";
import SourceCard from "./SourceCard";

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-neutral-900 text-white"
            : "bg-white border border-neutral-200 text-neutral-900"
        }`}
      >
        <div className="text-sm whitespace-pre-wrap leading-relaxed">
          {message.content}
        </div>
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourceCard sources={message.sources} />
        )}
        <p
          className={`text-[10px] mt-2 ${
            isUser ? "text-neutral-400" : "text-neutral-400"
          }`}
        >
          {message.timestamp.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}
