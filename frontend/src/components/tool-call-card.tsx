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
        <span className="text-[10px] text-zinc-650 bg-zinc-100 px-2 py-0.5 rounded-full border border-zinc-200 font-medium animate-pulse">
          Running
        </span>
      );
    }
    if (toolCall.error) {
      return (
        <span className="text-[10px] text-red-600 bg-red-50 px-2 py-0.5 rounded-full border border-red-100 font-medium flex items-center gap-0.5">
          <AlertTriangle className="w-2.5 h-2.5 text-red-500" />
          Failed
        </span>
      );
    }
    return (
      <span className="text-[10px] text-zinc-700 bg-zinc-100 px-2 py-0.5 rounded-full border border-zinc-200 font-medium">
        Success
      </span>
    );
  };

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-3 space-y-2 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold text-zinc-700">
          <Database className="w-3.5 h-3.5 text-orange-500" />
          <code className="text-zinc-900 font-mono text-[11px]">{toolCall.name}</code>
        </div>
        <div className="flex items-center gap-2">
          {statusBadge()}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 hover:bg-zinc-100 rounded text-zinc-500 hover:text-zinc-700 transition-colors"
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
        <div className="text-[11px] space-y-2 pt-2 border-t border-zinc-200 font-mono">
          <div className="bg-zinc-50 p-2.5 rounded-md border border-zinc-200">
            <div className="font-semibold text-zinc-500 mb-1 font-sans text-[10px] uppercase tracking-wider">
              Arguments
            </div>
            <pre className="text-zinc-700 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>
          {toolCall.result && (
            <div className="bg-zinc-50 p-2.5 rounded-md border border-zinc-200">
              <div className="font-semibold text-zinc-500 mb-1 font-sans text-[10px] uppercase tracking-wider">
                Result
              </div>
              <pre className="text-zinc-700 overflow-x-auto whitespace-pre-wrap">
                {toolCall.result}
              </pre>
            </div>
          )}
          {toolCall.error && (
            <div className="bg-red-50/30 p-2.5 rounded-md border border-red-100">
              <div className="font-semibold text-red-600 mb-1 font-sans text-[10px] uppercase tracking-wider">
                Error
              </div>
              <pre className="text-red-700 overflow-x-auto whitespace-pre-wrap">
                {toolCall.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
