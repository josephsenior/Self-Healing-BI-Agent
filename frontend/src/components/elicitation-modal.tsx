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
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center p-6 z-50">
      <div className="w-full max-w-lg rounded-lg bg-white border border-zinc-200 p-6 space-y-5 shadow-2xl animate-slide-up">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-zinc-200 pb-4">
          <div className="p-2 bg-orange-50 rounded-lg border border-orange-100">
            <ShieldAlert className="w-5 h-5 text-orange-500" />
          </div>
          <div>
            <h3 className="font-semibold text-zinc-900 text-base">Review before continuing</h3>
            <p className="text-[11px] text-zinc-400 uppercase tracking-wide">
            This action may change data, publish a report, or access an external service
            </p>
          </div>
        </div>

        {/* Message */}
        <div className="text-sm text-zinc-700 leading-relaxed bg-zinc-50 p-4 rounded-lg border border-zinc-200 border-l-2 border-l-orange-500">
          {elicitation.message}
        </div>

        {/* Form mode */}
        {elicitation.mode === "form" && elicitation.schema?.properties && (
          <div className="space-y-3">
            {Object.entries(elicitation.schema.properties).map(([key, prop]) => {
              const isRequired = elicitation.schema?.required?.includes(key);
              return (
                <div key={key} className="space-y-1.5">
                  <label className="text-[11px] font-semibold text-zinc-500 flex justify-between">
                    <span>{prop.description ?? key}</span>
                    {isRequired && (
                      <span className="text-red-500 text-[10px]">Required</span>
                    )}
                  </label>
                  {prop.type === "boolean" ? (
                    <div className="flex items-center gap-3 bg-zinc-50 p-3 rounded-lg border border-zinc-200">
                      <input
                        type="checkbox"
                        checked={Boolean(formData[key])}
                        onChange={(e) =>
                          setFormData((prev) => ({ ...prev, [key]: e.target.checked }))
                        }
                        className="w-4 h-4 text-orange-600 bg-white border-zinc-200 rounded focus:ring-orange-500"
                      />
                      <span className="text-xs text-zinc-600">Enable / Approve</span>
                    </div>
                  ) : (
                    <input
                      type="text"
                      value={String(formData[key] ?? "")}
                      onChange={(e) =>
                        setFormData((prev) => ({ ...prev, [key]: e.target.value }))
                      }
                      className="w-full bg-zinc-50 border border-zinc-200 rounded-lg p-2.5 text-xs text-zinc-800 focus:outline-none focus:border-orange-500 transition-colors"
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
            <p className="text-xs text-zinc-500">
              Visit the URL below to authenticate or grant consent:
            </p>
            <a
              href={elicitation.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 text-orange-600 hover:text-orange-700 underline text-xs font-semibold transition-colors"
            >
              <LinkIcon className="w-4 h-4" />
              <span>Open Elicitation URL</span>
            </a>
          </div>
        )}

        {/* Footer buttons */}
        <div className="flex gap-3 pt-4 border-t border-zinc-200 justify-end text-xs font-semibold">
          <button
            onClick={() => onRespond("cancel", {})}
            className="rounded-lg border border-zinc-200 bg-transparent px-4 py-2.5 text-zinc-600 transition-colors hover:bg-zinc-50 hover:text-zinc-900"
          >
            Cancel
          </button>
          <button
            onClick={() => onRespond("accept", formData)}
            className="px-5 py-2.5 bg-orange-500 hover:bg-orange-600 text-white border border-orange-600 rounded-lg transition-colors flex items-center gap-1.5 shadow-sm"
          >
            <CheckCircle className="w-4 h-4" />
            <span>Continue</span>
          </button>
        </div>
      </div>
    </div>
  );
}
