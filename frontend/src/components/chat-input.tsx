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
    <div className="p-4 border-t border-zinc-200 bg-white">
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="Ask about your Power BI data..."
          className="flex-1 bg-zinc-50 border border-zinc-200 focus:border-orange-500 rounded-lg px-4 py-3 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        />
        {isRunning ? (
          <button
            onClick={onAbort}
            className="px-4 py-3 bg-zinc-100 hover:bg-zinc-200 border border-zinc-200 text-zinc-700 rounded-lg transition-colors flex items-center gap-2 font-medium text-sm"
          >
            <Square className="w-4 h-4 text-zinc-500" />
            <span>Stop</span>
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={disabled || !value.trim()}
            className="px-4 py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-zinc-100 disabled:text-zinc-400 disabled:border-zinc-200 text-white rounded-lg transition-colors flex items-center gap-2 border border-orange-600 font-medium text-sm"
          >
            <SendHorizontal className="w-4 h-4" />
            <span>Send</span>
          </button>
        )}
      </div>
    </div>
  );
}
