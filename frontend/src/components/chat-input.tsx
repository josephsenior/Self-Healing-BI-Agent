"use client";

import React, { useEffect, useState } from "react";
import { SendHorizontal, Square, Sparkles } from "lucide-react";

interface ChatInputProps {
  onSend: (text: string) => void;
  onAbort: () => void;
  disabled: boolean;
  isRunning: boolean;
  inputRef?: React.RefObject<HTMLTextAreaElement>;
}

export function ChatInput({ onSend, onAbort, disabled, isRunning, inputRef }: ChatInputProps) {
  const [value, setValue] = useState("");

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef?.current?.focus();
      }
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, [inputRef]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="p-4 border-t border-zinc-200 bg-white">
      <div className="flex items-center gap-3">
        <textarea
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          disabled={disabled}
          rows={1}
          placeholder={disabled ? "Connect to Power BI to start analyzing…" : "Ask a question about your data…"}
          className="min-h-12 max-h-36 flex-1 resize-none overflow-y-auto rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm leading-relaxed text-zinc-900 outline-none transition-colors placeholder-zinc-400 focus:border-orange-500 focus:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        />
        {isRunning ? (
          <button
            onClick={onAbort}
            className="px-4 py-3 bg-zinc-100 hover:bg-zinc-200 border border-zinc-200 text-zinc-700 rounded-lg transition-colors flex items-center gap-2 font-medium text-sm"
          >
            <Square className="w-4 h-4 text-zinc-500" />
            <span>Stop analysis</span>
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={disabled || !value.trim()}
            className="px-4 py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-zinc-100 disabled:text-zinc-400 disabled:border-zinc-200 text-white rounded-lg transition-colors flex items-center gap-2 border border-orange-600 font-medium text-sm"
          >
            <SendHorizontal className="w-4 h-4" />
            <span>Analyze</span>
          </button>
        )}
      </div>
      <div className="mt-2 flex items-center justify-between px-1 text-[10px] text-zinc-400">
        <span className="flex items-center gap-1"><Sparkles className="size-3 text-orange-400" /> Try asking for insights, trends, or anomalies</span>
        <span>Enter to send · Shift+Enter for a new line</span>
      </div>
    </div>
  );
}
