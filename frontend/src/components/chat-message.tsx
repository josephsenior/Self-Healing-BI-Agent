"use client";

import React from "react";
import type { ChatMessage } from "@/types";
import { ToolCallCard } from "@/components/tool-call-card";

interface ChatMessageBubbleProps {
  message: ChatMessage;
}

export function ChatMessageBubble({ message }: ChatMessageBubbleProps) {
  const isUser = message.role === "user";

  const formattedTime = new Date(message.timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  return (
    <div
      className={`flex w-full animate-fade-in ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[75%] rounded-xl p-4 border text-sm leading-relaxed ${
          isUser
            ? "bg-blue-600/8 border-l-2 border-l-blue-500 border-slate-800/60"
            : "bg-slate-900/60 border-l-2 border-l-purple-500 border-slate-800/60"
        }`}
      >
        {/* Header: role + timestamp */}
        <div className="flex items-center justify-between mb-2">
          <span
            className={`text-[11px] font-semibold uppercase tracking-wider ${
              isUser ? "text-blue-400" : "text-purple-400"
            }`}
          >
            {isUser ? "You" : "Agent"}
          </span>
          <span className="text-[10px] text-slate-600 font-mono ml-4">{formattedTime}</span>
        </div>

        {/* Message content */}
        <div className="whitespace-pre-wrap text-slate-200">{message.content}</div>

        {/* Tool calls attached to this message */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mt-3 pt-3 border-t border-slate-800/60 space-y-2">
            {message.toolCalls.map((tc) => (
              <ToolCallCard key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
