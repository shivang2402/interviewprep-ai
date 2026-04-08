"use client";

import { useRef, useEffect } from "react";
import type { ChatMessage } from "@/lib/types";
import MessageBubble from "./MessageBubble";

interface MessageListProps {
  messages: ChatMessage[];
  loading: boolean;
}

export default function MessageList({ messages, loading }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  if (messages.length === 0 && !loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <h2 className="text-xl font-semibold text-neutral-900 mb-2">
            Interview Prep Assistant
          </h2>
          <p className="text-sm text-neutral-500 mb-6">
            Ask questions about real interview experiences from Google, Meta,
            Amazon, and more. Powered by RAG over thousands of interview reports.
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {[
              "How do I prepare for a Google SDE interview?",
              "What topics come up in Amazon system design rounds?",
              "Tell me about Meta frontend interview experience",
            ].map((q) => (
              <button
                key={q}
                className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs text-neutral-600 hover:bg-neutral-50 hover:border-neutral-300 transition-colors text-left"
                onClick={() => {
                  const event = new CustomEvent("suggestion-click", {
                    detail: q,
                  });
                  window.dispatchEvent(event);
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {loading && (
        <div className="flex justify-start">
          <div className="bg-white border border-neutral-200 rounded-2xl px-4 py-3">
            <div className="flex gap-1.5">
              <span className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
