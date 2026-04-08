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
          <div className="w-16 h-16 rounded-2xl bg-indigo-100 flex items-center justify-center mx-auto mb-5">
            <svg className="w-8 h-8 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
            </svg>
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
              "Tell me about Meta frontend interview experience",
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
