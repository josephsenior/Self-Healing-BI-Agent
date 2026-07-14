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
        <span className="text-[10px] text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full border border-blue-500/20 font-medium animate-pulse">
          Running
        </span>
      );
    }
    if (toolCall.error) {
      return (
        <span className="text-[10px] text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-full border border-rose-500/20 font-medium flex items-center gap-0.5">
          <AlertTriangle className="w-2.5 h-2.5" />
          Failed
        </span>
      );
    }
    return (
      <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20 font-medium">
        Success
      </span>
    );
  };

  return (
    <div className="rounded-lg border border-slate-800/60 bg-slate-950/40 p-3 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <Database className="w-3.5 h-3.5 text-blue-500" />
          <code className="text-blue-400 font-mono text-[11px]">{toolCall.name}</code>
        </div>
        <div className="flex items-center gap-2">
          {statusBadge()}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 hover:bg-slate-800 rounded text-slate-500 hover:text-slate-300 transition-colors"
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
        <div className="text-[11px] space-y-2 pt-2 border-t border-slate-800/40 font-mono">
          <div className="bg-slate-900/60 p-2.5 rounded-md border border-slate-800/40">
            <div className="font-semibold text-slate-500 mb-1 font-sans text-[10px] uppercase tracking-wider">
              Arguments
            </div>
            <pre className="text-slate-300 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>
          {toolCall.result && (
            <div className="bg-slate-900/60 p-2.5 rounded-md border border-slate-800/40">
              <div className="font-semibold text-slate-500 mb-1 font-sans text-[10px] uppercase tracking-wider">
                Result
              </div>
              <pre className="text-slate-300 overflow-x-auto whitespace-pre-wrap">
                {toolCall.result}
              </pre>
            </div>
          )}
          {toolCall.error && (
            <div className="bg-rose-950/20 p-2.5 rounded-md border border-rose-500/15">
              <div className="font-semibold text-rose-400/80 mb-1 font-sans text-[10px] uppercase tracking-wider">
                Error
              </div>
              <pre className="text-rose-300 overflow-x-auto whitespace-pre-wrap">
                {toolCall.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
