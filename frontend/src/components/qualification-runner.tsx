"use client";

import React, { useState, useEffect } from "react";
import { Play, RotateCcw, CheckCircle, AlertCircle, XCircle, ChevronDown, ChevronUp, Terminal, Database, Cloud, ShieldCheck } from "lucide-react";

interface QualificationRunnerProps {
  onComplete?: (result: any) => void;
}

interface QualStep {
  name: string;
  label: string;
  icon: React.ReactNode;
  status: "pending" | "running" | "complete" | "failed";
  details?: string;
  expandable?: boolean;
}

const STEPS: Omit<QualStep, "status" | "details">[] = [
  { name: "provision", label: "Provision Fabric Workspace", icon: <Cloud className="w-4 h-4" />, expandable: true },
  { name: "semantic_model", label: "Create Semantic Model", icon: <Database className="w-4 h-4" />, expandable: true },
  { name: "dashboard", label: "Build Dashboard Spec", icon: <ShieldCheck className="w-4 h-4" />, expandable: true },
  { name: "publish", label: "Publish to Fabric", icon: <Cloud className="w-4 h-4" />, expandable: true },
  { name: "render", label: "Render Report Pages", icon: <ShieldCheck className="w-4 h-4" />, expandable: true },
  { name: "visual_qa", label: "Visual QA Review", icon: <ShieldCheck className="w-4 h-4" />, expandable: true },
  { name: "iterate", label: "Iterate & Fix", icon: <RotateCcw className="w-4 h-4" />, expandable: true },
];

export function QualificationRunner({ onComplete }: QualificationRunnerProps) {
  const [steps, setSteps] = useState<QualStep[]>(STEPS.map(s => ({ ...s, status: "pending" as const })));
  const [running, setRunning] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [result, setResult] = useState<any>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const addLog = (message: string) => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${message}`]);
  };

  const runQualification = async () => {
    setRunning(true);
    setSteps(STEPS.map(s => ({ ...s, status: "pending" as const })));
    setLogs([]);
    setResult(null);
    setCurrentStepIndex(0);

    try {
      // Use the actual qualification endpoint
      addLog("Starting full autonomous agent qualification...");
      
      const res = await fetch("/api/qualification/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_visual_attempts: 3 }),
      });

      // Stream-like updates by polling or using the response
      // For now, simulate step progression while waiting
      const stepNames = ["provision", "semantic_model", "dashboard", "publish", "render", "visual_qa", "iterate"];
      
      for (let i = 0; i < stepNames.length; i++) {
        setCurrentStepIndex(i);
        setSteps(prev => prev.map((s, idx) => ({
          ...s,
          status: idx < i ? "complete" : idx === i ? "running" : "pending"
        })));
        addLog(`Step ${i + 1}/${stepNames.length}: ${STEPS[i].label}...`);
        await new Promise(r => setTimeout(r, 1000)); // Visual feedback
      }

      const data = await res.json();
      setResult(data);
      
      if (data.success) {
        setSteps(prev => prev.map(s => ({ ...s, status: "complete" })));
        addLog("✅ Qualification completed successfully!");
        if (data.semantic_model_id) addLog(`Semantic Model: ${data.semantic_model_id}`);
        if (data.report_id) addLog(`Report ID: ${data.report_id}`);
        if (data.workspace_id) addLog(`Workspace: ${data.workspace_id}`);
      } else {
        setSteps(prev => prev.map((s, idx) => idx === currentStepIndex ? { ...s, status: "failed" } : s));
        addLog(`❌ Qualification failed: ${data.error}`);
      }
      
      if (onComplete) onComplete(data);
    } catch (e) {
      setSteps(prev => prev.map((s, idx) => idx === currentStepIndex ? { ...s, status: "failed", details: String(e) } : s));
      addLog(`❌ Error: ${String(e)}`);
    } finally {
      setRunning(false);
      setCurrentStepIndex(-1);
    }
  };

  const getStepIcon = (step: QualStep) => {
    switch (step.status) {
      case "running": return <RotateCcw className="w-4 h-4 animate-spin text-orange-500" />;
      case "complete": return <CheckCircle className="w-4 h-4 text-emerald-500" />;
      case "failed": return <XCircle className="w-4 h-4 text-red-500" />;
      default: return <span className="w-4 h-4 text-zinc-300" />;
    }
  };

  return (
    <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-200 bg-zinc-50 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-500" />
          Autonomous Qualification
        </h3>
        <button
          onClick={runQualification}
          disabled={running}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-md transition-colors disabled:opacity-50"
          style={{
            backgroundColor: running ? "#71717A" : "#EA580C",
            color: "white",
            borderColor: running ? "#71717A" : "#EA580C",
          }}
        >
          {running ? (
            <>
              <RotateCcw className="w-3.5 h-3.5 animate-spin" />
              Running...
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5" />
              Run Full Qualification
            </>
          )}
        </button>
      </div>

      <div className="p-4 space-y-3">
        {/* Steps */}
        <div className="space-y-2">
          {steps.map((step, idx) => (
            <div key={step.name} className="group">
              <button
                onClick={() => step.expandable && setExpandedSteps(prev => {
                  const next = new Set(prev);
                  if (next.has(idx)) next.delete(idx);
                  else next.add(idx);
                  return next;
                })}
                className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-50 transition-colors"
              >
                <div className="flex items-center gap-2 w-8">{getStepIcon(step)}</div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-zinc-800">{step.label}</p>
                  {step.details && <p className="text-[10px] text-zinc-500">{step.details}</p>}
                </div>
                {step.status === "running" && <span className="text-[10px] bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded">Running</span>}
                {step.status === "complete" && <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">Done</span>}
                {step.status === "failed" && <span className="text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded">Failed</span>}
                {step.expandable && (
                  <span className={`text-zinc-400 transition-transform ${expandedSteps.has(idx) ? "rotate-180" : ""}`}>▼</span>
                )}
              </button>

              {expandedSteps.has(idx) && step.expandable && (
                <div className="ml-10 mt-1 pt-2 border-l border-zinc-200 pl-3 space-y-1 animate-in slide-in-from-top-2">
                  <p className="text-[11px] text-zinc-500">Step details would appear here during execution</p>
                  {step.status === "running" && <p className="text-[11px] text-orange-600">Currently executing...</p>}
                  {step.status === "complete" && <p className="text-[11px] text-emerald-600">Completed successfully</p>}
                  {step.status === "failed" && step.details && <p className="text-[11px] text-red-600">Error: {step.details}</p>}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Live Logs */}
        {logs.length > 0 && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">Live Logs</p>
              <button
                onClick={() => setLogs([])}
                className="text-[10px] text-zinc-400 hover:text-zinc-600"
              >
                Clear
              </button>
            </div>
            <div className="bg-zinc-950 rounded p-3 font-mono text-[10px] text-zinc-300 max-h-48 overflow-y-auto">
              {logs.map((log, i) => (
                <div key={i} className="border-t border-zinc-800 pt-1 first:border-0">
                  {log}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Final Result */}
        {result && (
          <div className={`mt-4 p-3 rounded-lg border ${result.success ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`}>
            <div className="flex items-center gap-2">
              {result.success ? (
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              ) : (
                <XCircle className="w-4 h-4 text-red-500" />
              )}
              <span className="font-medium text-sm">
                {result.success ? "Qualification Passed" : "Qualification Failed"}
              </span>
            </div>
            {result.error && <p className="text-sm text-red-700 mt-1">{result.error}</p>}
            {result.success && (
              <div className="mt-2 space-y-1 text-sm text-zinc-700">
                {result.semantic_model_id && <p><strong>Semantic Model:</strong> <code className="font-mono bg-white px-1 rounded">{result.semantic_model_id}</code></p>}
                {result.report_id && <p><strong>Report:</strong> <code className="font-mono bg-white px-1 rounded">{result.report_id}</code></p>}
                {result.workspace_id && <p><strong>Workspace:</strong> <code className="font-mono bg-white px-1 rounded">{result.workspace_id}</code></p>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}