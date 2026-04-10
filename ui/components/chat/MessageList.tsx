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
        <div className="text-center max-w-lg px-4">
          <div className="w-24 h-24 rounded-2xl flex items-center justify-center mx-auto mb-5">
            <img src="/logo.png" alt="InterviewPrep AI" className="w-24 h-24 object-contain rounded-2xl" />
          </div>
          <h2 className="text-2xl font-bold text-slate-900 mb-2">
            Interview Prep Assistant
          </h2>
          <p className="text-sm text-slate-500 mb-8 leading-relaxed">
            Ask questions about real interview experiences from Google, Meta,
            Amazon, and more. Powered by RAG over thousands of interview reports.
          </p>
          <div className="flex flex-col sm:flex-row flex-wrap justify-center gap-2.5">
            {[
              "How do I prepare for a Google SDE interview?",
              "What topics come up in Amazon system design rounds?",
              "Help me to prepare for SDE interview at Goldman Sachs",
            ].map((q) => (
              <button
                key={q}
                className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-600 hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-700 transition-all shadow-sm hover:shadow text-left"
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
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {loading && (
        <div className="flex justify-start">
          <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-md px-5 py-4 shadow-sm">
            <div className="dot-pulse flex gap-1.5">
              <span className="w-2 h-2 bg-indigo-400 rounded-full" />
              <span className="w-2 h-2 bg-indigo-400 rounded-full" />
              <span className="w-2 h-2 bg-indigo-400 rounded-full" />
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
