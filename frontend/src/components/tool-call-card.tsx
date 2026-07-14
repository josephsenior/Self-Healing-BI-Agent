"use client";

import React, { useState } from "react";
import { Database, ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";
import type { ToolCall } from "@/types";

interface ToolCallCardProps {
  toolCall: ToolCall;
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const statusBadge = () => {
    if (!toolCall.result && !toolCall.error) {
      return (
        <span className="text-[10px] text-zinc-300 bg-zinc-900 px-2 py-0.5 rounded-full border border-zinc-800 font-medium animate-pulse">
          Running
        </span>
      );
    }
    if (toolCall.error) {
      return (
        <span className="text-[10px] text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded-full border border-zinc-800 font-medium flex items-center gap-0.5">
          <AlertTriangle className="w-2.5 h-2.5 text-zinc-500" />
          Failed
        </span>
      );
    }
    return (
      <span className="text-[10px] text-zinc-300 bg-zinc-900 px-2 py-0.5 rounded-full border border-zinc-800 font-medium">
        Success
      </span>
    );
  };

  return (
    <div className="rounded-lg border border-zinc-850 bg-zinc-900/40 p-3 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold text-zinc-300">
          <Database className="w-3.5 h-3.5 text-zinc-500" />
          <code className="text-zinc-100 font-mono text-[11px]">{toolCall.name}</code>
        </div>
        <div className="flex items-center gap-2">
          {statusBadge()}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 hover:bg-zinc-800 rounded text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {isExpanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && (
        <div className="text-[11px] space-y-2 pt-2 border-t border-zinc-850/60 font-mono">
          <div className="bg-zinc-950 p-2.5 rounded-md border border-zinc-850">
            <div className="font-semibold text-zinc-500 mb-1 font-sans text-[10px] uppercase tracking-wider">
              Arguments
            </div>
            <pre className="text-zinc-300 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>
          {toolCall.result && (
            <div className="bg-zinc-950 p-2.5 rounded-md border border-zinc-850">
              <div className="font-semibold text-zinc-500 mb-1 font-sans text-[10px] uppercase tracking-wider">
                Result
              </div>
              <pre className="text-zinc-300 overflow-x-auto whitespace-pre-wrap">
                {toolCall.result}
              </pre>
            </div>
          )}
          {toolCall.error && (
            <div className="bg-zinc-950 p-2.5 rounded-md border border-zinc-850">
              <div className="font-semibold text-zinc-400 mb-1 font-sans text-[10px] uppercase tracking-wider">
                Error
              </div>
              <pre className="text-zinc-300 overflow-x-auto whitespace-pre-wrap">
                {toolCall.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
