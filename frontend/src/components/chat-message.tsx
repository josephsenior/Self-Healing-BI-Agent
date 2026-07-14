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
        className={`max-w-[75%] rounded-lg p-4 border text-sm leading-relaxed ${
          isUser
            ? "bg-zinc-50 border border-zinc-200 text-zinc-900"
            : "bg-white border border-zinc-200 text-zinc-900 shadow-sm"
        }`}
      >
        {/* Header: role + timestamp */}
        <div className="flex items-center justify-between mb-2">
          <span
            className={`text-[11px] font-semibold uppercase tracking-wider ${
              isUser ? "text-orange-600" : "text-zinc-900"
            }`}
          >
            {isUser ? "You" : "Agent"}
          </span>
          <span className="text-[10px] text-zinc-400 font-mono ml-4">{formattedTime}</span>
        </div>

        {/* Message content */}
        <div className="whitespace-pre-wrap text-zinc-800">{message.content}</div>

        {/* Tool calls attached to this message */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mt-3 pt-3 border-t border-zinc-200 space-y-2">
            {message.toolCalls.map((tc) => (
              <ToolCallCard key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
