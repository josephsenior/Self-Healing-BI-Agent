"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Layers, RotateCcw, ImageOff, CheckCircle, XCircle, ExternalLink } from "lucide-react";

interface PagesPanelProps {
  dashboardId: string;
  projectPath: string;
}

interface RenderedPage {
  index: number;
  name: string;
  path: string;
}

interface PagesResponse {
  success: boolean;
  error?: string;
  batch?: string;
  pages: RenderedPage[];
}

export function PagesPanel({ dashboardId, projectPath }: PagesPanelProps) {
  const [pages, setPages] = useState<RenderedPage[]>([]);
  const [batch, setBatch] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [rendering, setRendering] = useState(false);

  const fetchPages = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/dashboard/pages?report_id=${encodeURIComponent(dashboardId)}&project_path=${encodeURIComponent(projectPath)}`
      );
      const data: PagesResponse = await res.json();
      if (data.success) {
        setPages(data.pages || []);
        setBatch(data.batch || null);
        setError(null);
      } else {
        setPages([]);
        setError(data.error || "No rendered pages found");
      }
    } catch (e) {
      setPages([]);
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [dashboardId, projectPath]);

  useEffect(() => {
    fetchPages();
  }, [fetchPages]);

  const handleRender = async () => {
    setRendering(true);
    try {
      const res = await fetch("/api/dashboard/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_id: dashboardId }),
      });
      const data = await res.json();
      if (data.success) {
        await fetchPages();
      } else {
        setError(data.error || "Render failed");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setRendering(false);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-200 bg-zinc-50 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
          <Layers className="w-4 h-4 text-orange-500" />
          Report Pages
        </h3>
        <div className="flex items-center gap-2">
          {batch && (
            <span className="text-[10px] font-mono text-zinc-500 px-2 py-0.5 bg-zinc-100 rounded">
              {batch.slice(0, 8)}
            </span>
          )}
          <button
            onClick={handleRender}
            disabled={rendering}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-md bg-orange-500 text-white hover:bg-orange-600 transition-colors disabled:opacity-50"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${rendering ? "animate-spin" : ""}`} />
            {rendering ? "Rendering..." : "Render Pages"}
          </button>
        </div>
      </div>

      <div className="p-4">
        {loading && (
          <div className="flex items-center justify-center py-10">
            <RotateCcw className="w-5 h-5 text-orange-500 animate-spin" />
          </div>
        )}

        {!loading && error && !pages.length && (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <ImageOff className="w-6 h-6 text-zinc-300 mb-2" />
            <p className="text-sm text-zinc-600">{error}</p>
            <p className="text-xs text-zinc-400 mt-1">
              Publish the report to Fabric, then render pages to see them here.
            </p>
          </div>
        )}

        {!loading && pages.length > 0 && (
          <div className="space-y-6">
            {pages.map((page) => (
              <div key={page.path} className="border border-zinc-200 rounded-lg overflow-hidden bg-zinc-50">
                <div className="px-3 py-2 bg-white border-b border-zinc-200 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-orange-100 text-orange-600 flex items-center justify-center text-[10px] font-medium">
                      {page.index + 1}
                    </span>
                    <span className="text-sm font-medium text-zinc-800">{page.name}</span>
                  </div>
                  <a
                    href={`/api/preview?path=${encodeURIComponent(page.path)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-[11px] text-orange-600 hover:text-orange-700"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Open
                  </a>
                </div>
                <div className="p-2">
                  <img
                    src={`/api/preview?path=${encodeURIComponent(page.path)}`}
                    alt={page.name}
                    className="w-full rounded border border-zinc-200 bg-white shadow-sm"
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && pages.length === 0 && !error && (
          <div className="flex items-center justify-center py-10 text-sm text-zinc-500">
            No rendered pages available.
          </div>
        )}
      </div>
    </div>
  );
}