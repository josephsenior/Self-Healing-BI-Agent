"use client";

import React, { useState, useEffect } from "react";
import { BarChart3, RotateCcw, Palette, ShieldCheck, Cloud, Monitor, Database, Settings, ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import type { DashboardSpec, DashboardState, DashboardVersion, VisualSpec } from "@/types";
import { DashboardVersionTimeline } from "./dashboard-version-timeline";
import { VisualQAPanel } from "./visual-qa-panel";
import { ColorThemePicker } from "./color-theme-picker";
import { PublishPanel } from "./publish-panel";
import { DesktopLauncher } from "./desktop-launcher";
import { QualificationRunner } from "./qualification-runner";

interface DashboardManagerProps {
  dashboardId: string;
  projectPath: string;
  initialSpec?: DashboardSpec;
  initialState?: DashboardState;
}

export function DashboardManager({ dashboardId, projectPath, initialSpec, initialState }: DashboardManagerProps) {
  const [spec, setSpec] = useState<DashboardSpec | null>(initialSpec || null);
  const [state, setState] = useState<DashboardState | null>(initialState || null);
  const [versions, setVersions] = useState<DashboardVersion[]>([]);
  const [activeTab, setActiveTab] = useState<"overview" | "qa" | "colors" | "publish" | "desktop" | "qualification">("overview");
  const [loading, setLoading] = useState(true);

  const fetchDashboard = async () => {
    try {
      const [specRes, stateRes, versionsRes] = await Promise.all([
        fetch(`/api/dashboard/active?dashboard_id=${dashboardId}`),
        fetch(`/api/dashboard/active?dashboard_id=${dashboardId}`),
        fetch(`/api/dashboard/versions?dashboard_id=${dashboardId}`),
      ]);
      
      if (specRes.ok) {
        const specData = await specRes.json();
        setSpec(specData.spec);
      }
      if (stateRes.ok) {
        const stateData = await stateRes.json();
        setState(stateData);
      }
      if (versionsRes.ok) {
        const versionsData = await versionsRes.json();
        setVersions(versionsData.versions || []);
      }
    } catch (e) {
      console.error("Failed to fetch dashboard:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, [dashboardId]);

  const handleVisualUpdate = (updatedVisual: VisualSpec) => {
    if (!spec) return;
    const newSpec = {
      ...spec,
      pages: spec.pages.map(page => ({
        ...page,
        visuals: page.visuals.map(v => v === updatedVisual ? updatedVisual : v)
      }))
    };
    setSpec(newSpec);
  };

  const handleSpecChange = (newSpec: DashboardSpec) => {
    setSpec(newSpec);
  };

  const handleRollback = async (version: number) => {
    await fetchDashboard();
  };

  const handleRevise = (revisedSpec: any) => {
    setSpec(revisedSpec);
  };

  const handlePublished = (result: any) => {
    if (result.report_id) {
      setState(prev => prev ? { ...prev, published: true, rendered: false } : null);
    }
  };

  const visuals = spec?.pages.flatMap(p => p.visuals) || [];

  const tabs = [
    { id: "overview", label: "Overview", icon: BarChart3, count: visuals.length },
    { id: "qa", label: "Visual QA", icon: ShieldCheck, count: visuals.length },
    { id: "colors", label: "Colors", icon: Palette, count: visuals.length },
    { id: "publish", label: "Publish", icon: Cloud, count: visuals.length },
    { id: "desktop", label: "Desktop", icon: Monitor, count: visuals.length },
    { id: "qualification", label: "Qualification", icon: Sparkles, count: visuals.length },
  ] as const;

  if (loading) return <div className="text-center py-8 text-sm text-zinc-500">Loading dashboard...</div>;
  if (!spec) return <div className="text-center py-8 text-sm text-zinc-500">No dashboard found</div>;

  return (
    <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-200 bg-zinc-50">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 rounded-lg">
              <BarChart3 className="w-5 h-5 text-orange-500" />
            </div>
            <div>
              <h2 className="font-semibold text-zinc-900">{spec.title}</h2>
              <p className="text-sm text-zinc-500">{spec.pages.length} page(s) • {visuals.length} visual(s)</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {state && (
              <>
                {state.version != null && (
                  <span className="px-2 py-0.5 text-[10px] font-semibold text-orange-700 bg-orange-50 rounded border border-orange-200">
                    v{state.version}
                  </span>
                )}
                {state.published && (
                  <span className="px-2 py-0.5 text-[10px] font-semibold text-emerald-700 bg-emerald-50 rounded border border-emerald-200 flex items-center gap-1">
                    <Cloud className="w-3 h-3" /> Published
                  </span>
                )}
                {state.rendered && (
                   <span className="px-2 py-0.5 text-[10px] font-semibold text-orange-700 bg-orange-50 rounded border border-orange-200 flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3" /> QA Done
                  </span>
                )}
              </>
            )}
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-1 overflow-x-auto pb-1">
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors whitespace-nowrap ${
                  activeTab === tab.id
                    ? "bg-orange-500 text-white shadow-sm"
                    : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {tab.label}
                {tab.count != null && (
                  <span className={`px-1.5 py-0.5 text-[9px] font-mono rounded ${activeTab === tab.id ? "bg-orange-400 text-white" : "bg-zinc-200 text-zinc-600"}`}>
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {activeTab === "overview" && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="p-3 bg-zinc-50 rounded-lg border border-zinc-200">
                <p className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider mb-1">Dataset</p>
                <p className="font-mono text-sm text-zinc-700">{spec.dataset.path}</p>
              </div>
              <div className="p-3 bg-zinc-50 rounded-lg border border-zinc-200">
                <p className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider mb-1">Pages</p>
                <div className="space-y-1">
                  {spec.pages.map((page, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span className="w-5 h-5 rounded-full bg-orange-100 text-orange-600 flex items-center justify-center text-[10px] font-medium">{i + 1}</span>
                      <span className="font-medium text-zinc-800">{page.name}</span>
                      <span className="text-zinc-500">{page.visuals.length} visuals</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="p-3 bg-zinc-50 rounded-lg border border-zinc-200">
              <p className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider mb-2">Visual Summary</p>
              <div className="flex flex-wrap gap-2">
                {visuals.map((v, i) => (
                  <span key={i} className="px-2 py-1 text-[10px] font-mono bg-white border border-zinc-200 rounded">
                    {v.type} • {v.title}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === "qa" && (
          <VisualQAPanel
            dashboardId={dashboardId}
            projectPath={projectPath}
            onRevise={handleRevise}
          />
        )}

        {activeTab === "colors" && (
          <ColorThemePicker
            visuals={visuals}
            onUpdateVisual={handleVisualUpdate}
            dashboardSpec={spec}
            onSpecChange={handleSpecChange}
          />
        )}

        {activeTab === "publish" && (
          <PublishPanel
            dashboardId={state?.dashboard_id || dashboardId}
            projectPath={projectPath}
            displayName={spec.title}
            onPublished={handlePublished}
          />
        )}

        {activeTab === "desktop" && (
          <DesktopLauncher
            dashboardId={dashboardId}
            projectPath={projectPath}
          />
        )}

        {activeTab === "qualification" && (
          <QualificationRunner />
        )}
      </div>
    </div>
  );
}