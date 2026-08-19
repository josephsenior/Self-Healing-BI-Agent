"use client";

import React, { useState } from "react";
import { ShieldCheck, AlertTriangle, CheckCircle, XCircle, RotateCcw, Palette, Image, Download, ChevronDown, ChevronUp } from "lucide-react";

interface VisualQAProps {
  dashboardId: string;
  projectPath: string;
  onRevise: (findings: any) => void;
  onPublish?: () => void;
}

interface RenderResult {
  success: boolean;
  artifacts?: string[];
  error?: string;
}

interface ReviewResult {
  findings: any[];
  summary: string;
  passed: boolean;
}

interface QADecision {
  action: "accept" | "revise" | "max_attempts_reached";
  reason: string;
  revised_spec?: any;
}

export function VisualQAPanel({ dashboardId, projectPath, onRevise, onPublish }: VisualQAProps) {
  const [rendering, setRendering] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [renderResult, setRenderResult] = useState<RenderResult | null>(null);
  const [reviewResult, setReviewResult] = useState<ReviewResult | null>(null);
  const [qaDecision, setQADecision] = useState<QADecision | null>(null);
  const [expandedFinding, setExpandedFinding] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(1);

  const handleRender = async () => {
    setRendering(true);
    setRenderResult(null);
    setReviewResult(null);
    setQADecision(null);
    try {
      const res = await fetch("/api/dashboard/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_id: dashboardId }),
      });
      const data = await res.json();
      setRenderResult(data);
      if (data.success && data.artifacts?.length) {
        await handleReview(data.artifacts);
      }
    } catch (e) {
      setRenderResult({ success: false, error: String(e) });
    } finally {
      setRendering(false);
    }
  };

  const handleReview = async (artifacts: string[]) => {
    setReviewing(true);
    try {
      const res = await fetch("/api/dashboard/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ artifact_paths: artifacts, project_path: projectPath }),
      });
      const data = await res.json();
      setReviewResult({
        findings: data.findings || [],
        summary: data.summary || "",
        passed: data.passed || false,
      });
      await handleDecideQA(data);
    } catch (e) {
      console.error("Review failed:", e);
    } finally {
      setReviewing(false);
    }
  };

  const handleDecideQA = async (review: any) => {
    try {
      const res = await fetch("/api/dashboard/decide-qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ review, attempt, max_attempts: 3 }),
      });
      const data = await res.json();
      setQADecision(data);
      if (data.action === "revise" && data.revised_spec) {
        onRevise(data.revised_spec);
      }
    } catch (e) {
      console.error("QA decision failed:", e);
    }
  };

  const handleRetry = () => {
    setAttempt((a) => a + 1);
    handleRender();
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "error": return "text-red-600 bg-red-50 border-red-200";
      case "warning": return "text-amber-600 bg-amber-50 border-amber-200";
      case "info": return "text-blue-600 bg-blue-50 border-blue-200";
      default: return "text-zinc-600 bg-zinc-50 border-zinc-200";
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "error": return <XCircle className="w-3.5 h-3.5 text-red-500" />;
      case "warning": return <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />;
      case "info": return <ShieldCheck className="w-3.5 h-3.5 text-blue-500" />;
      default: return <ShieldCheck className="w-3.5 h-3.5 text-zinc-500" />;
    }
  };

  return (
    <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-200 bg-zinc-50 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-500" />
          Visual QA Inspector
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-zinc-500 px-2 py-0.5 bg-zinc-100 rounded">
            Attempt {attempt} / 3
          </span>
          <button
            onClick={handleRender}
            disabled={rendering || reviewing}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-md border border-zinc-200 bg-white hover:bg-zinc-50 transition-colors disabled:opacity-50"
          >
            {rendering || reviewing ? (
              <>
                <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                {rendering ? "Rendering..." : "Reviewing..."}
              </>
            ) : (
              <>
                <Image className="w-3.5 h-3.5" />
                Re-Inspect
              </>
            )}
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Render Status */}
        <div className={`p-3 rounded-lg border ${renderResult?.success ? "bg-emerald-50 border-emerald-200" : renderResult === null ? "bg-zinc-50 border-zinc-200" : "bg-red-50 border-red-200"}`}>
          <div className="flex items-center gap-2">
            {rendering && <RotateCcw className="w-4 h-4 animate-spin text-orange-500" />}
            {renderResult?.success && <CheckCircle className="w-4 h-4 text-emerald-500" />}
            {renderResult?.success === false && <XCircle className="w-4 h-4 text-red-500" />}
            <span className="text-sm font-medium text-zinc-800">
              {rendering
                ? "Rendering report pages..."
                : renderResult?.success
                ? `Rendered ${renderResult.artifacts?.length || 0} page(s)`
                : renderResult
                ? `Render failed: ${renderResult.error}`
                : "Not rendered yet"}
            </span>
          </div>
          {renderResult?.success && renderResult.artifacts && (
            <div className="mt-2 flex flex-wrap gap-2">
              {renderResult.artifacts.map((artifact, idx) => (
                <a
                  key={idx}
                  href={`/api/preview?path=${artifact}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-indigo-600 hover:text-indigo-700 font-mono flex items-center gap-1"
                >
                  <Image className="w-3 h-3" />
                  Page {idx + 1}
                </a>
              ))}
            </div>
          )}
        </div>

        {/* Review Findings */}
        {reviewResult && (
          <div className={`p-3 rounded-lg border ${reviewResult.passed ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"}`}>
            <div className="flex items-center gap-2 mb-2">
              {reviewResult.passed ? (
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-amber-500" />
              )}
              <span className="text-sm font-medium text-zinc-800">
                {reviewResult.passed ? "Visual QA Passed" : `Found ${reviewResult.findings.length} issue(s)`}
              </span>
            </div>
            {reviewResult.summary && (
              <p className="text-sm text-zinc-600 mb-3">{reviewResult.summary}</p>
            )}
            {reviewResult.findings.length > 0 && (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {reviewResult.findings.map((finding: any, idx: number) => (
                  <div
                    key={idx}
                    className={`p-3 rounded border ${getSeverityColor(finding.severity || "info")}`}
                  >
                    <div className="flex items-start gap-2">
                      {getSeverityIcon(finding.severity || "info")}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm text-zinc-800">{finding.title || "Issue"}</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/70">
                            {finding.severity?.toUpperCase() || "INFO"}
                          </span>
                          <button
                            onClick={() => setExpandedFinding(expandedFinding === idx ? null : idx)}
                            className="ml-auto text-zinc-400 hover:text-zinc-600"
                          >
                            {expandedFinding === idx ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                        <p className="text-sm text-zinc-700 mt-1">{finding.description || finding.message}</p>
                        {finding.visual_id && (
                          <span className="text-[10px] font-mono text-zinc-500 mt-1 block">Visual: {finding.visual_id}</span>
                        )}
                        {finding.suggestion && (
                          <p className="text-sm text-zinc-600 mt-1"><strong>Suggestion:</strong> {finding.suggestion}</p>
                        )}
                        {expandedFinding === idx && finding.details && (
                          <pre className="mt-2 p-2 bg-white/50 rounded text-[10px] font-mono text-zinc-700 overflow-x-auto max-h-32">
                            {JSON.stringify(finding.details, null, 2)}
                          </pre>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* QA Decision */}
        {qaDecision && (
          <div className={`p-3 rounded-lg border ${
            qaDecision.action === "accept" ? "bg-emerald-50 border-emerald-200" :
            qaDecision.action === "revise" ? "bg-blue-50 border-blue-200" :
            "bg-red-50 border-red-200"
          }`}>
            <div className="flex items-center gap-2">
              {qaDecision.action === "accept" && <CheckCircle className="w-4 h-4 text-emerald-500" />}
              {qaDecision.action === "revise" && <Palette className="w-4 h-4 text-blue-500" />}
              {qaDecision.action === "max_attempts_reached" && <XCircle className="w-4 h-4 text-red-500" />}
              <span className="text-sm font-medium text-zinc-800 capitalize">{qaDecision.action.replace("_", " ")}</span>
            </div>
            <p className="text-sm text-zinc-600 mt-1">{qaDecision.reason}</p>
            {qaDecision.action === "revise" && (
              <button
                onClick={() => handleRetry()}
                className="mt-2 flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-md bg-blue-500 text-white hover:bg-blue-600 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Apply Fix & Re-Inspect
              </button>
            )}
            {qaDecision.action === "max_attempts_reached" && onPublish && (
              <button
                onClick={onPublish}
                className="mt-2 flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-md border border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors"
              >
                Publish Anyway
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}