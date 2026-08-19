"use client";

import React, { useState, useEffect } from "react";
import { Cloud, ShieldCheck, AlertCircle, XCircle, RotateCcw, CheckCircle, WifiOff, Key, Monitor, ArrowUpRight } from "lucide-react";
import type { CloudReadiness } from "@/types";

interface PublishPanelProps {
  dashboardId: string;
  projectPath: string;
  displayName: string;
  onPublished: (result: any) => void;
}

export function PublishPanel({ dashboardId, projectPath, displayName, onPublished }: PublishPanelProps) {
  const [readiness, setReadiness] = useState<CloudReadiness | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [expandedChecks, setExpandedChecks] = useState(false);

  const checkReadiness = async () => {
    try {
      const res = await fetch("/api/dashboard/cloud-readiness");
      if (res.ok) {
        const data = await res.json();
        setReadiness(data);
      }
    } catch (e) {
      console.error("Failed to check readiness:", e);
    }
  };

  useEffect(() => {
    checkReadiness();
  }, []);

  const handlePublish = async () => {
    setPublishing(true);
    setResult(null);
    try {
      const res = await fetch("/api/dashboard/publish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_path: projectPath, display_name: displayName }),
      });
      const data = await res.json();
      setResult(data);
      if (data.report_id || data.id) {
        onPublished(data);
      }
    } catch (e) {
      setResult({ error: String(e) });
    } finally {
      setPublishing(false);
    }
  };

  const getCheckIcon = (key: string, value: boolean) => {
    if (key === "vision_provider" || key === "license_mode") return null;
    return value ? <CheckCircle className="w-4 h-4 text-emerald-500" /> : <XCircle className="w-4 h-4 text-red-500" />;
  };

  const getCheckLabel = (key: string) => {
    const labels: Record<string, string> = {
      workspace_id: "Workspace ID configured",
      fabric_auth: "Fabric authentication",
      powerbi_auth: "Power BI authentication",
      vision_provider: "Vision provider",
      vision_model: "Vision model configured",
      vision_api_key: "Vision API key",
    };
    return labels[key] || key;
  };

  if (!readiness) return <div className="text-center py-4 text-sm text-zinc-500">Checking cloud readiness...</div>;

  return (
    <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-200 bg-zinc-50 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
          <Cloud className="w-4 h-4 text-orange-500" />
          Publish to Fabric
        </h3>
        <button onClick={checkReadiness} className="p-1 text-zinc-400 hover:text-zinc-600" title="Refresh">
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Overall Status */}
        <div className={`p-4 rounded-lg border ${readiness.publishing_ready ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`}>
          <div className="flex items-center gap-3">
            {readiness.publishing_ready ? (
              <CheckCircle className="w-6 h-6 text-emerald-500" />
            ) : (
              <XCircle className="w-6 h-6 text-red-500" />
            )}
            <div>
              <p className="font-medium text-zinc-800">
                {readiness.publishing_ready ? "Ready to Publish" : "Publishing Not Ready"}
              </p>
              <p className="text-sm text-zinc-600 mt-0.5">
                {readiness.publishing_ready
                  ? "All required credentials and workspace are configured."
                  : "Missing required configuration. Expand checks below for details."}
              </p>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-sm">
            <span className={`px-2 py-0.5 rounded font-mono ${readiness.license_mode === "capacity" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
              {readiness.license_mode.toUpperCase()}
            </span>
            <span className="text-zinc-500">License Mode</span>
            {!readiness.rendering_supported && (
              <span className="flex items-center gap-1 text-amber-600 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                <WifiOff className="w-3 h-3" />
                No PNG Rendering (ExportToFile unsupported)
              </span>
            )}
          </div>
        </div>

        {/* Checks */}
        <details className="group" open={expandedChecks} onToggle={() => setExpandedChecks(!expandedChecks)}>
          <summary className="flex items-center justify-between cursor-pointer p-2 rounded hover:bg-zinc-50">
            <span className="text-sm font-medium text-zinc-700">Configuration Checks</span>
            <span className="text-zinc-400 transition-transform group-open:rotate-180">▼</span>
          </summary>
          <div className="px-2 pb-2 space-y-2 border-t border-zinc-100 mt-2">
            {Object.entries(readiness.checks).map(([key, value]) => {
                const val = value as unknown;
                return (
                  <div key={key} className="flex items-center justify-between p-2 rounded bg-zinc-50">
                    <div className="flex items-center gap-2">
                      {getCheckIcon(key, value as boolean)}
                      <div>
                        <p className="text-sm font-medium text-zinc-800">{getCheckLabel(key)}</p>
                        {key === "vision_provider" && typeof val === "string" && (
                          <p className="text-[10px] text-zinc-500 capitalize">{val.toUpperCase()}</p>
                        )}
                        {key === "license_mode" && typeof val === "string" && (
                          <p className="text-[10px] text-zinc-500 capitalize">{val}</p>
                        )}
                      </div>
                    </div>
                    {typeof val === "boolean" && (
                      <span className={`${(val as boolean) ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"} text-[10px] font-mono px-2 py-0.5 rounded`}>
                        {(val as boolean) ? "OK" : "MISSING"}
                      </span>
                    )}
                  </div>
                );
              })}
          </div>
        </details>

        {/* Limitations */}
        {readiness.limitations.length > 0 && (
          <div className="p-3 rounded-lg bg-amber-50 border border-amber-200">
            <p className="text-sm font-medium text-amber-800 mb-1">Limitations</p>
            <ul className="text-sm text-amber-700 space-y-1">
              {readiness.limitations.map((l, i) => (
                <li key={i} className="flex items-start gap-2">
                  <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  {l}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Publish Button */}
        <button
          onClick={handlePublish}
          disabled={publishing || !readiness.publishing_ready}
          className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-medium transition-colors ${
            publishing
              ? "bg-zinc-300 text-zinc-500 cursor-not-allowed"
              : readiness.publishing_ready
              ? "bg-orange-500 text-white hover:bg-orange-600"
              : "bg-zinc-100 text-zinc-400 cursor-not-allowed"
          }`}
        >
          {publishing ? (
            <>
              <RotateCcw className="w-4 h-4 animate-spin" />
              Publishing...
            </>
          ) : (
            <>
              <ArrowUpRight className="w-4 h-4" />
              Publish to Fabric
            </>
          )}
        </button>

        {/* Result */}
        {result && (
          <div className={`p-3 rounded-lg border ${result.error ? "bg-red-50 border-red-200" : "bg-emerald-50 border-emerald-200"}`}>
            <div className="flex items-center gap-2">
              {result.error ? (
                <XCircle className="w-4 h-4 text-red-500" />
              ) : (
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              )}
              <span className="font-medium text-sm">
                {result.error ? "Publish Failed" : "Published Successfully"}
              </span>
            </div>
            {result.error && <p className="text-sm text-red-700 mt-1">{result.error}</p>}
            {!result.error && (
              <div className="mt-2 space-y-1 text-sm">
                <p className="text-zinc-700"><strong>Report ID:</strong> {result.report_id || result.id}</p>
                {result.web_url && (
                  <a href={result.web_url} target="_blank" rel="noopener noreferrer" className="text-orange-600 hover:underline flex items-center gap-1">
                    <Monitor className="w-3.5 h-3.5" />
                    Open in Power BI Service
                  </a>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}