"use client";

import React, { useState } from "react";
import { ShieldAlert, CheckCircle, Link as LinkIcon } from "lucide-react";
import type { ElicitationRequest } from "@/types";

interface ElicitationModalProps {
  elicitation: ElicitationRequest;
  onRespond: (
    action: "accept" | "decline" | "cancel",
    content: Record<string, unknown>
  ) => void;
}

export function ElicitationModal({ elicitation, onRespond }: ElicitationModalProps) {
  const [formData, setFormData] = useState<Record<string, unknown>>(() => {
    const initial: Record<string, unknown> = {};
    if (elicitation.schema?.properties) {
      Object.entries(elicitation.schema.properties).forEach(([key, prop]) => {
        initial[key] = prop.default ?? "";
      });
    }
    return initial;
  });

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6 z-50">
      <div className="w-full max-w-lg rounded-2xl bg-[#0e1322] border border-slate-800 p-6 space-y-5 shadow-2xl shadow-blue-900/10 animate-slide-up">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
          <div className="p-2 bg-amber-500/15 rounded-lg">
            <ShieldAlert className="w-5 h-5 text-amber-500" />
          </div>
          <div>
            <h3 className="font-bold text-slate-100 text-base">Human Approval Required</h3>
            <p className="text-[11px] text-slate-500 uppercase tracking-wide">
              Enterprise Write Safety Guard
            </p>
          </div>
        </div>

        {/* Message */}
        <div className="text-sm text-slate-300 leading-relaxed bg-slate-900/40 p-4 rounded-xl border border-slate-800/80 border-l-2 border-l-amber-500/50">
          {elicitation.message}
        </div>

        {/* Form mode */}
        {elicitation.mode === "form" && elicitation.schema?.properties && (
          <div className="space-y-3">
            {Object.entries(elicitation.schema.properties).map(([key, prop]) => {
              const isRequired = elicitation.schema?.required?.includes(key);
              return (
                <div key={key} className="space-y-1.5">
                  <label className="text-[11px] font-semibold text-slate-400 flex justify-between">
                    <span>{prop.description ?? key}</span>
                    {isRequired && (
                      <span className="text-rose-500 text-[10px]">Required</span>
                    )}
                  </label>
                  {prop.type === "boolean" ? (
                    <div className="flex items-center gap-3 bg-slate-900/30 p-3 rounded-lg border border-slate-800">
                      <input
                        type="checkbox"
                        checked={Boolean(formData[key])}
                        onChange={(e) =>
                          setFormData((prev) => ({ ...prev, [key]: e.target.checked }))
                        }
                        className="w-4 h-4 text-blue-600 bg-slate-900 border-slate-800 rounded focus:ring-blue-500"
                      />
                      <span className="text-xs text-slate-300">Enable / Approve</span>
                    </div>
                  ) : (
                    <input
                      type="text"
                      value={String(formData[key] ?? "")}
                      onChange={(e) =>
                        setFormData((prev) => ({ ...prev, [key]: e.target.value }))
                      }
                      className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500 transition-colors"
                      placeholder={`Enter ${key}...`}
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* URL mode */}
        {elicitation.mode === "url" && elicitation.url && (
          <div className="space-y-2">
            <p className="text-xs text-slate-400">
              Visit the URL below to authenticate or grant consent:
            </p>
            <a
              href={elicitation.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 text-blue-400 hover:text-blue-300 underline text-xs font-semibold transition-colors"
            >
              <LinkIcon className="w-4 h-4" />
              <span>Open Elicitation URL</span>
            </a>
          </div>
        )}

        {/* Footer buttons */}
        <div className="flex gap-3 pt-4 border-t border-slate-800 justify-end text-xs font-semibold">
          <button
            onClick={() => onRespond("decline", {})}
            className="px-4 py-2.5 bg-transparent border border-slate-700 text-slate-400 hover:bg-slate-800 hover:text-slate-200 rounded-xl transition-colors"
          >
            Decline
          </button>
          <button
            onClick={() => onRespond("accept", formData)}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-slate-100 rounded-xl border border-blue-500/20 transition-colors flex items-center gap-1.5"
          >
            <CheckCircle className="w-4 h-4" />
            <span>Approve</span>
          </button>
        </div>
      </div>
    </div>
  );
}
