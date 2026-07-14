"use client";

import React, { useState } from "react";
import { SendHorizontal, Square } from "lucide-react";

interface ChatInputProps {
  onSend: (text: string) => void;
  onAbort: () => void;
  disabled: boolean;
  isRunning: boolean;
}

export function ChatInput({ onSend, onAbort, disabled, isRunning }: ChatInputProps) {
  const [value, setValue] = useState("");

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="p-4 border-t border-slate-800/60 bg-[#0a0f1e]/80 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Ask about your Power BI data..."
          className="flex-1 bg-slate-900/80 border border-slate-800 focus:border-blue-500 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-600 focus:outline-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        />
        {isRunning ? (
          <button
            onClick={onAbort}
            className="px-4 py-3 bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/30 text-rose-400 rounded-xl transition-colors flex items-center gap-2 font-semibold text-sm"
          >
            <Square className="w-4 h-4" />
            <span>Stop</span>
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={disabled || !value.trim()}
            className="px-4 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 disabled:border-slate-800 rounded-xl transition-colors flex items-center gap-2 border border-blue-500/30 font-semibold text-sm"
          >
            <SendHorizontal className="w-4 h-4" />
            <span>Send</span>
          </button>
        )}
      </div>
    </div>
  );
}
