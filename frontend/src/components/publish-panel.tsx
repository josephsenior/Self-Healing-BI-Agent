"use client";

import React, { useState, useEffect } from "react";
import {
  Cloud,
  ShieldCheck,
  AlertCircle,
  XCircle,
  RotateCcw,
  CheckCircle,
  WifiOff,
  Key,
  Monitor,
  ArrowUpRight,
  ExternalLink,
  Copy,
  Check,
  Building2,
  Database,
  Lock,
  Layers,
  Sparkles,
} from "lucide-react";
import type { CloudReadiness } from "@/types";

interface PublishPanelProps {
  dashboardId: string;
  projectPath: string;
  displayName: string;
  onPublished: (result: any) => void;
}

export function PublishPanel({
  dashboardId,
  projectPath,
  displayName,
  onPublished,
}: PublishPanelProps) {
  const [readiness, setReadiness] = useState<CloudReadiness | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [copied, setCopied] = useState(false);
  const [semanticModelId, setSemanticModelId] = useState("");
  const [customReportName, setCustomReportName] = useState(displayName || "");
  const [expandedChecks, setExpandedChecks] = useState(false);

  useEffect(() => {
    setCustomReportName(displayName || "");
  }, [displayName]);

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
        body: JSON.stringify({
          project_path: projectPath,
          display_name: customReportName.trim() || displayName,
          semantic_model_id: semanticModelId.trim() || undefined,
        }),
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

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getCheckIcon = (key: string, value: boolean) => {
    if (key === "vision_provider" || key === "license_mode") return null;
    return value ? (
      <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
    ) : (
      <XCircle className="w-4 h-4 text-rose-500 shrink-0" />
    );
  };

  const getCheckLabel = (key: string) => {
    const labels: Record<string, string> = {
      workspace_id: "Fabric / Power BI Workspace ID",
      fabric_auth: "Microsoft Fabric Auth (Bearer Token / Entra ID)",
      powerbi_auth: "Power BI REST API Auth",
      vision_provider: "AI Visual Inspection Provider",
      vision_model: "Visual QA Model Configured",
      vision_api_key: "Vision API Key",
    };
    return labels[key] || key;
  };

  if (!readiness) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <RotateCcw className="w-6 h-6 text-orange-500 animate-spin mb-2" />
        <p className="text-xs text-zinc-500 font-medium">Checking Microsoft Fabric cloud readiness…</p>
      </div>
    );
  }

  const webUrl =
    result?.web_url ||
    (result?.workspace_id && result?.report_id
      ? `https://app.powerbi.com/groups/${result.workspace_id}/reports/${result.report_id}`
      : null);

  return (
    <div className="bg-white rounded-xl border border-zinc-200 shadow-xs overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-100 bg-zinc-50/70 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-orange-50 text-orange-600 flex items-center justify-center border border-orange-100">
            <Cloud className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-semibold text-zinc-900 leading-none">Microsoft Fabric Publishing</h3>
            <p className="text-[11px] text-zinc-400 mt-0.5 leading-none">Deploy PBIR report directly to Fabric workspace</p>
          </div>
        </div>
        <button
          onClick={checkReadiness}
          className="p-1.5 text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 rounded-md transition-colors"
          title="Refresh readiness status"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Readiness Status Card */}
        <div
          className={`p-3.5 rounded-xl border transition-all ${
            readiness.publishing_ready
              ? "bg-emerald-50/60 border-emerald-200/80 text-emerald-900"
              : "bg-amber-50/60 border-amber-200/80 text-amber-900"
          }`}
        >
          <div className="flex items-start gap-3">
            {readiness.publishing_ready ? (
              <CheckCircle className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-xs font-semibold">
                  {readiness.publishing_ready
                    ? "Fabric Workspace Ready"
                    : "Fabric Configuration Incomplete"}
                </p>
                <span
                  className={`px-1.5 py-0.2 text-[10px] font-mono rounded font-medium ${
                    readiness.license_mode === "capacity"
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  {readiness.license_mode.toUpperCase()}
                </span>
              </div>
              <p className="text-xs text-zinc-600 mt-1 leading-relaxed">
                {readiness.publishing_ready
                  ? "Connected to Fabric workspace. Ready to deploy the live PBIR definition."
                  : "Missing Fabric API access token or workspace credentials. Configure them below or via .env."}
              </p>
            </div>
          </div>
        </div>

        {/* Deployment Inputs */}
        <div className="space-y-3 p-3.5 rounded-xl bg-zinc-50/60 border border-zinc-200/70">
          <div className="space-y-1">
            <label className="text-[11px] font-semibold text-zinc-700">Report Display Name</label>
            <input
              type="text"
              value={customReportName}
              onChange={(e) => setCustomReportName(e.target.value)}
              placeholder="e.g. Executive Sales Performance"
              className="w-full px-3 py-1.5 text-xs bg-white border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 transition-colors"
            />
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-semibold text-zinc-700">Fabric Semantic Model ID (Optional)</label>
              <span className="text-[10px] text-zinc-400">Direct Lake / Import</span>
            </div>
            <input
              type="text"
              value={semanticModelId}
              onChange={(e) => setSemanticModelId(e.target.value)}
              placeholder="UUID of target Fabric semantic model (if re-binding)"
              className="w-full px-3 py-1.5 text-xs bg-white border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 transition-colors font-mono"
            />
          </div>
        </div>

        {/* Configuration Checks Accordion */}
        <div className="border border-zinc-200/80 rounded-xl overflow-hidden">
          <button
            type="button"
            onClick={() => setExpandedChecks(!expandedChecks)}
            className="w-full flex items-center justify-between p-3 text-left bg-zinc-50/50 hover:bg-zinc-100/60 transition-colors"
          >
            <span className="text-xs font-semibold text-zinc-700 flex items-center gap-2">
              <Building2 className="w-3.5 h-3.5 text-zinc-500" />
              <span>Environment & Credential Checks</span>
            </span>
            <span className="text-xs text-zinc-400 font-mono">
              {Object.values(readiness.checks).filter(Boolean).length} / {Object.keys(readiness.checks).length}
            </span>
          </button>

          {expandedChecks && (
            <div className="p-3 border-t border-zinc-100 space-y-2 bg-white">
              {Object.entries(readiness.checks).map(([key, value]) => {
                const val = value as unknown;
                return (
                  <div key={key} className="flex items-center justify-between p-2 rounded-lg bg-zinc-50 border border-zinc-100">
                    <div className="flex items-center gap-2.5 min-w-0">
                      {getCheckIcon(key, value as boolean)}
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-zinc-800 truncate">{getCheckLabel(key)}</p>
                        {key === "vision_provider" && typeof val === "string" && (
                          <p className="text-[10px] text-zinc-500 uppercase">{val}</p>
                        )}
                      </div>
                    </div>
                    {typeof val === "boolean" && (
                      <span
                        className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded ${
                          val ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {val ? "READY" : "MISSING"}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Publish Action Button */}
        <button
          type="button"
          onClick={handlePublish}
          disabled={publishing || !readiness.publishing_ready}
          className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold shadow-xs transition-all ${
            publishing
              ? "bg-zinc-200 text-zinc-500 cursor-not-allowed"
              : readiness.publishing_ready
              ? "bg-orange-600 hover:bg-orange-700 text-white active:scale-[0.99]"
              : "bg-zinc-100 text-zinc-400 cursor-not-allowed"
          }`}
        >
          {publishing ? (
            <>
              <RotateCcw className="w-3.5 h-3.5 animate-spin" />
              <span>Deploying to Microsoft Fabric…</span>
            </>
          ) : (
            <>
              <Cloud className="w-3.5 h-3.5" />
              <span>Publish to Microsoft Fabric</span>
            </>
          )}
        </button>

        {/* Publish Result Card */}
        {result && (
          <div
            className={`p-4 rounded-xl border animate-fade-in ${
              result.error
                ? "bg-rose-50/80 border-rose-200 text-rose-900"
                : "bg-emerald-50/80 border-emerald-200 text-emerald-900"
            }`}
          >
            <div className="flex items-center gap-2 mb-2">
              {result.error ? (
                <XCircle className="w-4 h-4 text-rose-600 shrink-0" />
              ) : (
                <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
              )}
              <p className="text-xs font-semibold">
                {result.error ? "Deployment Failed" : "Successfully Published to Fabric"}
              </p>
            </div>

            {result.error ? (
              <p className="text-xs text-rose-700 leading-relaxed font-mono bg-white/60 p-2.5 rounded-lg border border-rose-100">
                {result.error}
              </p>
            ) : (
              <div className="space-y-3">
                <div className="p-2.5 bg-white/80 rounded-lg border border-emerald-100 space-y-1.5 text-xs text-zinc-700">
                  <div className="flex items-center justify-between">
                    <span className="text-zinc-500">Report ID:</span>
                    <span className="font-mono font-medium text-zinc-900">{result.report_id || result.id}</span>
                  </div>
                  {result.workspace_id && (
                    <div className="flex items-center justify-between">
                      <span className="text-zinc-500">Workspace ID:</span>
                      <span className="font-mono text-zinc-800">{result.workspace_id}</span>
                    </div>
                  )}
                </div>

                {webUrl && (
                  <div className="flex items-center gap-2">
                    <a
                      href={webUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-xs transition-colors"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      <span>Open in Power BI Service</span>
                    </a>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(webUrl)}
                      className="p-2 rounded-lg bg-white border border-emerald-200 text-zinc-600 hover:text-zinc-900 hover:bg-emerald-50 transition-colors shrink-0"
                      title="Copy URL"
                    >
                      {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}