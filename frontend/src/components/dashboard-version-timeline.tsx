"use client";

import React, { useState, useEffect } from "react";
import { RotateCcw, ChevronDown, ChevronUp, FileText, Clock, AlertCircle, CheckCircle, XCircle } from "lucide-react";
import type { DashboardVersion, DashboardSpec } from "@/types";

interface DashboardVersionTimelineProps {
  dashboardId: string;
  onRollback: (version: number) => void;
  onViewSpec: (spec: DashboardSpec) => void;
  currentVersion: number;
}

export function DashboardVersionTimeline({ dashboardId, onRollback, onViewSpec, currentVersion }: DashboardVersionTimelineProps) {
  const [versions, setVersions] = useState<DashboardVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedVersion, setExpandedVersion] = useState<number | null>(null);
  const [rollingBack, setRollingBack] = useState<number | null>(null);

  const fetchVersions = async () => {
    try {
      const res = await fetch(`/api/dashboard/versions?dashboard_id=${dashboardId}`);
      if (res.ok) {
        const data = await res.json();
        setVersions(data.versions || []);
      }
    } catch (e) {
      console.error("Failed to fetch versions:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchVersions();
  }, [dashboardId]);

  const handleRollback = async (version: number) => {
    if (!confirm(`Rollback to version ${version}? This will create a new version with the rolled-back spec.`)) return;
    setRollingBack(version);
    try {
      const res = await fetch("/api/dashboard/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dashboard_id: dashboardId, target_version: version }),
      });
      if (res.ok) {
        await fetchVersions();
        onRollback(version);
      } else {
        alert("Rollback failed");
      }
    } catch (e) {
      alert("Rollback failed");
    } finally {
      setRollingBack(null);
    }
  };

  if (loading) return <div className="text-center py-4 text-sm text-zinc-500">Loading versions...</div>;
  if (!versions.length) return <div className="text-center py-4 text-sm text-zinc-500">No versions yet</div>;

  return (
    <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-200 bg-zinc-50">
        <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
          <Clock className="w-4 h-4 text-orange-500" />
          Version History ({versions.length})
        </h3>
      </div>
      <div className="divide-y divide-zinc-100 max-h-96 overflow-y-auto">
        {versions.slice().reverse().map((v) => (
          <div key={v.version} className="relative">
            <button
              onClick={() => setExpandedVersion(expandedVersion === v.version ? null : v.version)}
              className="w-full px-4 py-3 flex items-center gap-3 hover:bg-zinc-50 transition-colors text-left"
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <div className={`flex items-center gap-2 ${v.version === currentVersion ? "text-emerald-600" : "text-zinc-600"}`}>
                  <span className="font-mono text-sm font-medium">v{v.version}</span>
                  {v.version === currentVersion && (
                    <span title="Current version">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                    </span>
                  )}
                  {rollingBack === v.version && (
                    <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Rolling back...</span>
                  )}
                </div>
                <span className="text-[11px] text-zinc-500 truncate max-w-[200px]">{v.reason}</span>
                <span className="text-[10px] text-zinc-400 whitespace-nowrap">{new Date(v.created_at).toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-1">
                {expandedVersion === v.version ? (
                  <ChevronUp className="w-4 h-4 text-zinc-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-zinc-400" />
                )}
              </div>
            </button>

            {expandedVersion === v.version && (
              <div className="px-4 pb-3 bg-zinc-50/50 border-t border-zinc-100 animate-in slide-in-from-top-2 duration-150">
                <div className="space-y-2 mt-2 pt-2 border-t border-zinc-100">
                  <button
                    onClick={() => onViewSpec(v.spec)}
                    className="w-full flex items-center justify-center gap-2 text-sm text-zinc-600 hover:text-zinc-900 hover:bg-white px-3 py-1.5 rounded border border-zinc-200 transition-colors"
                  >
                    <FileText className="w-3.5 h-3.5" />
                    View Full Spec
                  </button>
                  {v.version !== currentVersion && !rollingBack && (
                    <button
                      onClick={() => handleRollback(v.version)}
                      className="w-full flex items-center justify-center gap-2 text-sm text-orange-600 hover:text-orange-700 hover:bg-orange-50 px-3 py-1.5 rounded border border-orange-200 transition-colors"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      Rollback to This Version
                    </button>
                  )}
                </div>
                <div className="mt-2 p-2 bg-white rounded border border-zinc-100 overflow-x-auto">
                  <pre className="text-[10px] font-mono text-zinc-700 max-h-48 overflow-y-auto">
                    {JSON.stringify(v.spec, null, 2).slice(0, 2000)}
                    {JSON.stringify(v.spec, null, 2).length > 2000 && "..."}
                  </pre>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}