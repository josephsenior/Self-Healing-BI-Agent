"use client";

import React, { useState } from "react";
import { Monitor, RotateCcw, CheckCircle, AlertCircle, Database, Play, ExternalLink } from "lucide-react";

interface DesktopLauncherProps {
  dashboardId: string;
  projectPath: string;
}

export function DesktopLauncher({ dashboardId, projectPath }: DesktopLauncherProps) {
  const [opening, setOpening] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [semanticModelPath, setSemanticModelPath] = useState("");

  const handleOpen = async () => {
    setOpening(true);
    setResult(null);
    try {
      const res = await fetch("/api/dashboard/open-desktop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          dashboard_id: dashboardId,
          semantic_model_path: semanticModelPath || undefined,
        }),
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      setResult({ error: String(e), opened: false });
    } finally {
      setOpening(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-200 bg-zinc-50">
        <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
          <Monitor className="w-4 h-4 text-orange-500" />
          Open in Power BI Desktop
        </h3>
      </div>

      <div className="p-4 space-y-4">
        <div className="p-3 bg-zinc-50 rounded-lg border border-zinc-200">
          <p className="text-sm text-zinc-700 mb-2">
            Launch the current dashboard version in your local Power BI Desktop with a synthetic data model for immediate preview.
          </p>
          <div className="space-y-2">
            <div>
              <label className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider block mb-1">
                Semantic Model Path (optional)
              </label>
              <input
                type="text"
                value={semanticModelPath}
                onChange={(e) => setSemanticModelPath(e.target.value)}
                placeholder="Leave empty to auto-generate staging model"
                className="w-full text-sm font-mono bg-white border border-zinc-200 rounded px-2 py-1.5 focus:outline-none focus:border-orange-500"
              />
              <p className="text-[10px] text-zinc-400 mt-1">
                Provide a .SemanticModel folder path, or leave blank to auto-create a staging model with synthetic data.
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={handleOpen}
          disabled={opening}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-medium transition-colors bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50"
        >
          {opening ? (
            <>
              <RotateCcw className="w-4 h-4 animate-spin" />
              Launching Power BI Desktop...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Open in Power BI Desktop
            </>
          )}
        </button>

        {result && (
          <div className={`p-3 rounded-lg border ${result.opened ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`}>
            <div className="flex items-center gap-2">
              {result.opened ? (
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              ) : (
                <AlertCircle className="w-4 h-4 text-red-500" />
              )}
              <span className="font-medium text-sm">
                {result.opened ? "Launched Successfully" : "Launch Failed"}
              </span>
            </div>
            {result.opened && (
              <div className="mt-2 space-y-1 text-sm text-zinc-700">
                <p><strong>Opened:</strong> {result.opened_file || "definition.pbir"}</p>
                {result.semantic_model_path && (
                  <p><strong>Model:</strong> <code className="font-mono bg-white px-1 rounded">{result.semantic_model_path}</code></p>
                )}
                {result.version && <p><strong>Version:</strong> {result.version}</p>}
              </div>
            )}
            {result.error && (
              <p className="text-sm text-red-700 mt-2">{result.error}</p>
            )}
            {result.opened && result.pbir_path && (
              <a
                href={result.pbir_path}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-sm text-orange-600 hover:underline"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Open .pbip folder
              </a>
            )}
          </div>
        )}

        <div className="pt-2 border-t border-zinc-100">
          <p className="text-[10px] text-zinc-500 text-center">
            Requires Power BI Desktop installed on this machine. The report opens with a synthetic
            staging model unless you provide a semantic model path.
          </p>
        </div>
      </div>
    </div>
  );
}