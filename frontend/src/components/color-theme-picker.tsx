"use client";

import React, { useState } from "react";
import { Palette, Eye, Copy, Check, ChevronDown, ChevronUp, Brush, SlidersHorizontal } from "lucide-react";
import type { VisualSpec } from "@/types";

const PRESET_THEMES = [
  { name: "Crimson Red", color: "#DC2626", bg: "#FEF2F2" },
  { name: "Emerald Green", color: "#059669", bg: "#ECFDF5" },
  { name: "Royal Blue", color: "#2563EB", bg: "#EFF6FF" },
  { name: "Amber Gold", color: "#D97706", bg: "#FFFBEB" },
  { name: "Violet Purple", color: "#7C3AED", bg: "#F5F3FF" },
  { name: "Rose Pink", color: "#E11D48", bg: "#FFF1F2" },
  { name: "Teal", color: "#0D9488", bg: "#F0FDFA" },
  { name: "Orange", color: "#EA580C", bg: "#FFF7ED" },
];

const PRESET_PALETTES = [
  { name: "Warm", colors: ["#DC2626", "#EA580C", "#D97706", "#CA8A04", "#E11D48"] },
  { name: "Cool", colors: ["#2563EB", "#0D9488", "#059669", "#7C3AED", "#4F46E5"] },
  { name: "Monochrome", colors: ["#111827", "#374151", "#6B7280", "#9CA3AF", "#D1D5DB"] },
  { name: "Pastel", colors: ["#FCA5A5", "#FDBA74", "#FDE047", "#86EFAC", "#67E8F9", "#A5B4FC", "#FBCFE8"] },
  { name: "Corporate", colors: ["#1E3A8A", "#1E40AF", "#3B82F6", "#60A5FA", "#93C5FD"] },
];

interface ColorThemePickerProps {
  visuals: VisualSpec[];
  onUpdateVisual: (visual: VisualSpec) => void;
  dashboardSpec: any;
  onSpecChange: (spec: any) => void;
}

export function ColorThemePicker({ visuals, onUpdateVisual, dashboardSpec, onSpecChange }: ColorThemePickerProps) {
  const [customColor, setCustomColor] = useState("#DC2626");
  const [selectedVisualIndex, setSelectedVisualIndex] = useState<number | null>(null);
  const [showPalette, setShowPalette] = useState(false);
  const [showCustomPicker, setShowCustomPicker] = useState(false);
  const [applyingToAll, setApplyingToAll] = useState(false);

  const chartVisuals = visuals.filter(v => 
    ["barChart", "lineChart", "areaChart", "pieChart", "donutChart", "scatterChart", 
     "clusteredColumnChart", "stackedColumnChart", "clusteredBarChart", "stackedBarChart",
     "ribbonChart", "funnel", "waterfallChart", "gauge", "lineStackedColumnComboChart",
     "lineClusteredColumnComboChart", "treemap", "hundredPercentStackedColumnChart",
     "hundredPercentStackedBarChart", "stackedAreaChart"].includes(v.type)
  );

  const cardVisuals = visuals.filter(v => ["card", "multiRowCard", "kpi"].includes(v.type));

  const applyColorToVisual = (visual: VisualSpec, color: string) => {
    const updated = { ...visual, font_color: color };
    onUpdateVisual(updated);
  };

  const applyColorToAllCharts = (color: string) => {
    chartVisuals.forEach(v => applyColorToVisual(v, color));
  };

  const applyColorToAllCards = (color: string) => {
    cardVisuals.forEach(v => applyColorToVisual(v, color));
  };

  const applyColorToAll = (color: string) => {
    visuals.forEach(v => applyColorToVisual(v, color));
  };

  const handlePresetClick = (color: string) => {
    if (selectedVisualIndex !== null) {
      applyColorToVisual(visuals[selectedVisualIndex], color);
    } else if (applyingToAll) {
      applyColorToAll(color);
    } else {
      applyColorToAllCharts(color);
    }
    setCustomColor(color);
  };

  const handlePalettePresetClick = (palette: typeof PRESET_PALETTES[0]) => {
    chartVisuals.forEach((v, idx) => {
      const color = palette.colors[idx % palette.colors.length];
      applyColorToVisual(v, color);
    });
  };

  const getVisualColor = (visual: VisualSpec) => visual.font_color || "#000000";

  return (
    <div className="bg-white rounded-lg border border-zinc-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-zinc-200 bg-zinc-50 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-zinc-900 flex items-center gap-2">
          <Palette className="w-4 h-4 text-orange-500" />
          Color Theme Picker
        </h3>
        <label className="flex items-center gap-2 text-sm text-zinc-600 cursor-pointer">
          <input
            type="checkbox"
            checked={applyingToAll}
            onChange={(e) => setApplyingToAll(e.target.checked)}
            className="w-3.5 h-3.5 rounded border-zinc-300 text-orange-500 focus:ring-orange-500"
          />
          Apply to all visuals
        </label>
      </div>

      <div className="p-4 space-y-4">
        {/* Color Mode Selector */}
        <div className="flex gap-2">
          <button
            onClick={() => { setShowPalette(false); setShowCustomPicker(false); }}
            className={`flex-1 px-3 py-2 text-sm font-medium rounded border transition-colors ${
              !showPalette && !showCustomPicker
                ? "bg-orange-500 text-white border-orange-500"
                : "bg-white text-zinc-600 border-zinc-200 hover:bg-zinc-50"
            }`}
          >
            <Brush className="w-3.5 h-3.5 mr-1" />
            Single Color
          </button>
          <button
            onClick={() => { setShowPalette(true); setShowCustomPicker(false); }}
            className={`flex-1 px-3 py-2 text-sm font-medium rounded border transition-colors ${
              showPalette
                ? "bg-orange-500 text-white border-orange-500"
                : "bg-white text-zinc-600 border-zinc-200 hover:bg-zinc-50"
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5 mr-1" />
            Palettes
          </button>
          <button
            onClick={() => { setShowCustomPicker(true); setShowPalette(false); }}
            className={`flex-1 px-3 py-2 text-sm font-medium rounded border transition-colors ${
              showCustomPicker
                ? "bg-orange-500 text-white border-orange-500"
                : "bg-white text-zinc-600 border-zinc-200 hover:bg-zinc-50"
            }`}
          >
            <Eye className="w-3.5 h-3.5 mr-1" />
            Custom
          </button>
        </div>

        {/* Single Color Mode */}
        {(!showPalette && !showCustomPicker) && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 p-3 bg-zinc-50 rounded-lg border border-zinc-200">
              <input
                type="color"
                value={customColor}
                onChange={(e) => handlePresetClick(e.target.value)}
                className="w-12 h-12 rounded border border-zinc-300 cursor-pointer"
                title="Current color"
              />
              <div className="flex-1">
                <input
                  type="text"
                  value={customColor}
                  onChange={(e) => {
                    if (/^#[0-9A-Fa-f]{6}$/.test(e.target.value)) {
                      setCustomColor(e.target.value);
                      handlePresetClick(e.target.value);
                    }
                  }}
                  className="font-mono text-sm bg-white border border-zinc-200 rounded px-2 py-1 w-24"
                  placeholder="#RRGGBB"
                />
                <p className="text-[11px] text-zinc-500 mt-1">Click color swatch or enter hex</p>
              </div>
              <button
                onClick={() => navigator.clipboard.writeText(customColor)}
                className="p-2 text-zinc-400 hover:text-zinc-600 transition-colors"
                title="Copy hex"
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>

            <div>
              <p className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider mb-2">Presets</p>
              <div className="flex flex-wrap gap-2">
                {PRESET_THEMES.map((theme) => (
                  <button
                    key={theme.name}
                    onClick={() => handlePresetClick(theme.color)}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-colors hover:shadow-sm"
                    style={{ backgroundColor: theme.bg, borderColor: theme.color }}
                  >
                    <span className="w-3 h-3 rounded" style={{ backgroundColor: theme.color }} />
                    <span className="text-sm font-medium text-zinc-800">{theme.name}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Palette Mode */}
        {showPalette && (
          <div className="space-y-4">
            <p className="text-sm text-zinc-600">Click a palette to cycle colors across all chart visuals</p>
            <div className="space-y-3">
              {PRESET_PALETTES.map((palette) => (
                <button
                  key={palette.name}
                  onClick={() => handlePalettePresetClick(palette)}
                  className="w-full p-3 rounded-lg border border-zinc-200 hover:border-orange-300 hover:bg-orange-50 transition-colors text-left"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-medium text-zinc-800">{palette.name}</span>
                    <span className="text-[10px] text-zinc-500">{palette.colors.length} colors</span>
                  </div>
                  <div className="flex gap-1">
                    {palette.colors.map((color, idx) => (
                      <span
                        key={idx}
                        className="flex-1 h-5 rounded border border-zinc-200"
                        style={{ backgroundColor: color }}
                        title={color}
                      />
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Custom Color Picker */}
        {showCustomPicker && (
          <div className="space-y-4">
            <div className="flex items-center gap-4 p-3 bg-zinc-50 rounded-lg border border-zinc-200">
              <input
                type="color"
                value={customColor}
                onChange={(e) => setCustomColor(e.target.value)}
                className="w-16 h-16 rounded border border-zinc-300 cursor-pointer"
              />
              <div className="flex-1">
                <input
                  type="text"
                  value={customColor}
                  onChange={(e) => {
                    if (/^#[0-9A-Fa-f]{6}$/.test(e.target.value)) {
                      setCustomColor(e.target.value);
                    }
                  }}
                  className="font-mono text-sm bg-white border border-zinc-200 rounded px-3 py-2 w-32 mb-2"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => handlePresetClick(customColor)}
                    className="px-4 py-2 bg-orange-500 text-white text-sm font-medium rounded hover:bg-orange-600 transition-colors"
                  >
                    Apply to Charts
                  </button>
                  <button
                    onClick={() => applyColorToAll(customColor)}
                    className="px-4 py-2 bg-zinc-100 text-zinc-700 text-sm font-medium rounded border border-zinc-200 hover:bg-zinc-200 transition-colors"
                  >
                    Apply to All
                  </button>
                </div>
              </div>
            </div>
            <p className="text-sm text-zinc-500">Set a custom hex color and apply to selected visuals</p>
          </div>
        )}

        {/* Visual Selector */}
        <div className="pt-2 border-t border-zinc-100">
          <p className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider mb-2">
            Visual Colors ({visuals.length} total)
          </p>
          <div className="max-h-64 overflow-y-auto space-y-1">
            {visuals.map((visual, idx) => {
              const color = getVisualColor(visual);
              const isChart = chartVisuals.some(v => v === visual);
              const isCard = cardVisuals.some(v => v === visual);
              return (
                <button
                  key={idx}
                  onClick={() => setSelectedVisualIndex(selectedVisualIndex === idx ? null : idx)}
                  className={`w-full flex items-center gap-3 p-2 rounded-lg border transition-colors ${
                    selectedVisualIndex === idx
                      ? "bg-orange-50 border-orange-200"
                      : "bg-white border-zinc-200 hover:bg-zinc-50"
                  }`}
                >
                  <span
                    className="w-5 h-5 rounded border border-zinc-200 flex-shrink-0"
                    style={{ backgroundColor: color }}
                    title={color}
                  />
                  <div className="flex-1 min-w-0 text-left">
                    <p className="text-sm font-medium text-zinc-800 truncate">{visual.title || visual.type}</p>
                    <p className="text-[10px] text-zinc-500 font-mono">{visual.type} • {color}</p>
                  </div>
                  {selectedVisualIndex === idx && <Check className="w-4 h-4 text-orange-500" />}
                </button>
              );
            })}
          </div>
          {selectedVisualIndex !== null && (
            <p className="text-[11px] text-orange-600 mt-2 text-center">
              Click a preset above to apply to "{visuals[selectedVisualIndex].title}"
            </p>
          )}
        </div>
      </div>
    </div>
  );
}