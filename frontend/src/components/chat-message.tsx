"use client";

import React, { useState, useEffect, useRef } from "react";
import type { ChatMessage } from "@/types";
import { ToolCallCard } from "@/components/tool-call-card";
import { MarkdownRenderer } from "@/components/markdown-renderer";

interface ChatMessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean; // true while this is the last message and agent is running
}

// ─── Minimal Streaming Reasoning Strip ───────────────────────────────────────

function ReasoningStrip({
  text,
  isStreaming,
}: {
  text: string;
  isStreaming: boolean;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll the reasoning strip while streaming
  useEffect(() => {
    if (isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [text, isStreaming]);


  if (!text) return null;

  return (
    <div className="mb-3 select-none">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex items-center gap-2 w-full text-left group"
        aria-label="Toggle reasoning"
      >
        {/* Animated brain dot */}
        <span className="relative flex-shrink-0 flex items-center justify-center w-4 h-4">
          <span
            className={`absolute inline-block w-2 h-2 rounded-full ${
              isStreaming
                ? "bg-violet-400 animate-ping opacity-75"
                : "bg-violet-300"
            }`}
          />
          <span className="relative inline-block w-1.5 h-1.5 rounded-full bg-violet-500" />
        </span>

        {/* Label */}
        <span className="text-[10px] font-semibold text-violet-500 uppercase tracking-widest">
          {isStreaming ? "Thinking…" : "Reasoning"}
        </span>

        {/* Word count */}
        <span className="text-[9px] text-zinc-300 font-mono ml-auto">
          {text.split(/\s+/).filter(Boolean).length}w
        </span>

        {/* Collapse chevron */}
        <svg
          className={`w-3 h-3 text-zinc-400 transition-transform duration-200 ${
            collapsed ? "-rotate-90" : ""
          }`}
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* Body — visible when not collapsed */}
      <div
        className={`overflow-hidden transition-all duration-300 ease-out ${
          collapsed ? "max-h-0 opacity-0" : "max-h-60 opacity-100"
        }`}
      >
        <div
          ref={scrollRef}
          className="mt-1.5 max-h-52 overflow-y-auto scroll-smooth"
        >
          <p className="text-[11px] text-zinc-400 leading-relaxed font-sans italic pl-6 border-l border-violet-200/40">
            {text}
            {isStreaming && (
              <span className="inline-block w-0.5 h-3 bg-violet-400 ml-0.5 animate-pulse align-middle" />
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Main bubble ─────────────────────────────────────────────────────────────

export function ChatMessageBubble({
  message,
  isStreaming = false,
}: ChatMessageBubbleProps) {
  const isUser = message.role === "user";

  const formattedTime = new Date(message.timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  // Strip any leftover <thinking>…</thinking> tags from display content
  const displayContent = (message.content || "")
    .replace(/<thinking>[\s\S]*?<\/thinking>/g, "")
    .trim();

  const reasoningText = message.reasoningContent || "";
  // Reasoning is actively streaming when there's reasoning text, no display content yet,
  // and the agent is currently running
  const reasoningStreaming = isStreaming && !!reasoningText && !displayContent;

  return (
    <div className={`flex w-full animate-fade-in ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[78%] rounded-xl px-4 py-3 text-sm leading-relaxed border ${
          isUser
            ? "bg-zinc-50 border-zinc-200 text-zinc-900"
            : "bg-white border-zinc-200 text-zinc-900 shadow-sm"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-2.5">
          <span
            className={`text-[10px] font-bold uppercase tracking-widest ${
              isUser ? "text-orange-500" : "text-zinc-400"
            }`}
          >
            {isUser ? "You" : "Agent"}
          </span>
          <span className="text-[10px] text-zinc-300 font-mono">{formattedTime}</span>
        </div>

        {/* Render parts in exact chronological timing order if present */}
        {!isUser && message.parts && message.parts.length > 0 ? (
          <div className="space-y-3">
            {message.parts.map((part, pIdx) => {
              const isLastPart = pIdx === message.parts!.length - 1;
              if (part.type === "reasoning") {
                return (
                  <ReasoningStrip
                    key={`reasoning-${pIdx}`}
                    text={part.text}
                    isStreaming={isStreaming && isLastPart}
                  />
                );
              }
              if (part.type === "tool_call") {
                return (
                  <div key={part.toolCall.id || `tc-${pIdx}`} className="my-1.5">
                    <ToolCallCard toolCall={part.toolCall} />
                  </div>
                );
              }
              if (part.type === "text") {
                const cleanedText = part.text
                  .replace(/<thinking>[\s\S]*?<\/thinking>/g, "")
                  .trim();
                if (!cleanedText && !isStreaming) return null;
                return (
                  <div key={`text-${pIdx}`}>
                    {cleanedText && (
                      <MarkdownRenderer
                        content={cleanedText}
                        isStreaming={isStreaming && isLastPart}
                      />
                    )}
                    {isStreaming && isLastPart && (
                      <span className="inline-block w-0.5 h-3.5 bg-zinc-400 ml-0.5 animate-pulse align-middle" />
                    )}
                  </div>
                );
              }
              return null;
            })}
          </div>
        ) : (
          <>
            {/* Fallback for legacy assistant messages or User messages */}
            {!isUser && reasoningText && (
              <ReasoningStrip text={reasoningText} isStreaming={reasoningStreaming} />
            )}

            {displayContent && (
              isUser ? (
                <div className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
                  {displayContent}
                </div>
              ) : (
                <MarkdownRenderer content={displayContent} isStreaming={isStreaming} />
              )
            )}

            {isStreaming && displayContent && (
              <span className="inline-block w-0.5 h-3.5 bg-zinc-400 ml-0.5 animate-pulse align-middle" />
            )}

            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="mt-3 pt-3 border-t border-zinc-100 space-y-2">
                {message.toolCalls.map((tc) => (
                  <ToolCallCard key={tc.id} toolCall={tc} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
