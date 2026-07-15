"use client";

import React, { useState } from "react";
import { Database, ChevronDown, ChevronUp, AlertTriangle, Monitor, TableProperties, FileCode } from "lucide-react";
import type { ToolCall } from "@/types";

interface ToolCallCardProps {
  toolCall: ToolCall;
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const statusBadge = () => {
    if (!toolCall.result && !toolCall.error) {
      return (
        <span className="text-[10px] text-zinc-600 bg-zinc-100 px-2 py-0.5 rounded-full border border-zinc-200 font-medium animate-pulse">
          Running
        </span>
      );
    }
    if (toolCall.error) {
      return (
        <span className="text-[10px] text-red-600 bg-red-50 px-2 py-0.5 rounded-full border border-red-100 font-medium flex items-center gap-0.5">
          <AlertTriangle className="w-2.5 h-2.5 text-red-505" />
          Failed
        </span>
      );
    }
    return (
      <span className="text-[10px] text-green-700 bg-green-50 px-2 py-0.5 rounded-full border border-green-100 font-medium">
        Success
      </span>
    );
  };

  // Helper to parse JSON safely
  const tryParseJson = (str?: string) => {
    if (!str) return null;
    try {
      return JSON.parse(str);
    } catch {
      return null;
    }
  };

  const parsedResult = tryParseJson(toolCall.result);
  const args = toolCall.arguments as any;

  const isConnectionList =
    toolCall.name === "connection_operations" &&
    (args?.request?.operation === "ListLocalInstances" ||
      args?.operation === "ListLocalInstances") &&
    Array.isArray(parsedResult);

  const isDaxQueryResult =
    toolCall.name === "dax_query_operations" &&
    Array.isArray(parsedResult);

  const isMeasureOp =
    toolCall.name === "measure_operations" &&
    (args?.request?.operation === "CreateMeasure" ||
      args?.request?.operation === "UpdateMeasure" ||
      args?.operation === "CreateMeasure" ||
      args?.operation === "UpdateMeasure");

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-3 space-y-2 shadow-sm animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold text-zinc-700">
          <Database className="w-3.5 h-3.5 text-orange-500" />
          <code className="text-zinc-950 font-mono text-[11px]">{toolCall.name}</code>
        </div>
        <div className="flex items-center gap-2">
          {statusBadge()}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 hover:bg-zinc-100 rounded text-zinc-500 hover:text-zinc-700 transition-colors"
          >
            {isExpanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Rich UX UI Renderers (inline when result/error is loaded) */}
      {toolCall.result && (
        <div className="pt-1">
          {isConnectionList && (
            <div className="mt-1">
              <div className="flex items-center gap-1 text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">
                <Monitor className="w-3 h-3 text-zinc-400" />
                <span>Local Power BI Instances</span>
              </div>
              <LocalInstancesList data={parsedResult} />
            </div>
          )}

          {isDaxQueryResult && (
            <div className="mt-1">
              <div className="flex items-center gap-1 text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">
                <TableProperties className="w-3.5 h-3.5 text-zinc-400" />
                <span>DAX Query Results</span>
              </div>
              <DaxQueryGrid data={parsedResult} />
            </div>
          )}

          {isMeasureOp && (
            <div className="mt-1">
              <div className="flex items-center gap-1 text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">
                <FileCode className="w-3.5 h-3.5 text-zinc-400" />
                <span>Measure Specification</span>
              </div>
              <MeasureBuilder args={toolCall.arguments} />
            </div>
          )}
        </div>
      )}

      {/* Expanded details */}
      {isExpanded && (
        <div className="text-[11px] space-y-2 pt-2 border-t border-zinc-200 font-mono">
          <div className="bg-zinc-50 p-2.5 rounded-md border border-zinc-200">
            <div className="font-semibold text-zinc-500 mb-1 font-sans text-[10px] uppercase tracking-wider">
              Arguments
            </div>
            <pre className="text-zinc-700 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>
          {!isConnectionList && !isDaxQueryResult && !isMeasureOp && toolCall.result && (
            <div className="bg-zinc-50 p-2.5 rounded-md border border-zinc-200">
              <div className="font-semibold text-zinc-500 mb-1 font-sans text-[10px] uppercase tracking-wider">
                Result
              </div>
              <pre className="text-zinc-700 overflow-x-auto whitespace-pre-wrap">
                {toolCall.result}
              </pre>
            </div>
          )}
          {toolCall.error && (
            <div className="bg-red-50/30 p-2.5 rounded-md border border-red-100">
              <div className="font-semibold text-red-650 mb-1 font-sans text-[10px] uppercase tracking-wider">
                Error
              </div>
              <pre className="text-red-700 overflow-x-auto whitespace-pre-wrap">
                {toolCall.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DaxQueryGrid({ data }: { data: any[] }) {
  if (!Array.isArray(data) || data.length === 0) {
    return <div className="text-zinc-500 italic py-1 text-xs">Empty dataset returned.</div>;
  }

  const columns = Object.keys(data[0]);

  return (
    <div className="overflow-x-auto border border-zinc-200 rounded-md my-2 max-h-[300px]">
      <table className="min-w-full divide-y divide-zinc-200 text-left text-xs text-zinc-700">
        <thead className="bg-zinc-50 sticky top-0 border-b border-zinc-200">
          <tr>
            {columns.map((col) => (
              <th key={col} className="px-3 py-2 font-semibold text-zinc-900 bg-zinc-50 border-r border-zinc-200 last:border-r-0 font-sans">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-150 bg-white">
          {data.map((row, idx) => (
            <tr key={idx} className="hover:bg-zinc-50/50 transition-colors">
              {columns.map((col) => {
                const val = row[col];
                const displayVal = typeof val === "object" && val !== null ? JSON.stringify(val) : String(val ?? "");
                return (
                  <td key={col} className="px-3 py-1.5 font-mono text-[11px] border-r border-zinc-100 last:border-r-0 whitespace-nowrap text-zinc-800">
                    {displayVal}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LocalInstancesList({ data }: { data: any[] }) {
  if (!Array.isArray(data) || data.length === 0) {
    return <div className="text-zinc-500 italic py-1 text-xs">No active local instances found.</div>;
  }

  return (
    <div className="grid grid-cols-1 gap-2 my-2">
      {data.map((inst, idx) => (
        <div key={idx} className="flex items-center justify-between p-3 rounded-lg border border-zinc-200 bg-zinc-50/50 hover:bg-zinc-50 transition-all shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-orange-100 text-orange-600">
              <span className="text-[10px] font-bold font-mono">PBI</span>
            </div>
            <div>
              <div className="font-semibold text-zinc-900 text-xs">
                {inst.connectionName || "Power BI Desktop"}
              </div>
              <div className="text-[10px] text-zinc-500 font-mono">
                Port: {inst.port}
              </div>
            </div>
          </div>
          <span className="text-[9px] text-green-700 bg-green-50 px-2 py-0.5 rounded border border-green-150 font-medium">
            Available
          </span>
        </div>
      ))}
    </div>
  );
}

function MeasureBuilder({ args }: { args: any }) {
  const req = args?.request || args;
  const name = req.name || req.measureName || "";
  const table = req.tableName || "";
  const expression = req.expression || "";

  return (
    <div className="p-3 rounded-lg border border-zinc-200 bg-zinc-50/30 my-2 space-y-2">
      <div className="flex items-center justify-between text-xs border-b border-zinc-200/60 pb-2">
        <div>
          <span className="text-zinc-500 mr-1.5 font-sans text-[10px] uppercase tracking-wider">Table:</span>
          <span className="font-mono text-zinc-950 font-bold">{table}</span>
        </div>
        <div>
          <span className="text-zinc-500 mr-1.5 font-sans text-[10px] uppercase tracking-wider">Measure:</span>
          <span className="font-mono text-orange-600 font-bold">[{name}]</span>
        </div>
      </div>
      {expression && (
        <div>
          <div className="text-[10px] text-zinc-500 font-sans uppercase tracking-wider mb-1 font-semibold">DAX Expression</div>
          <pre className="bg-zinc-950 text-zinc-100 p-3 rounded border border-zinc-800 font-mono text-[11px] overflow-x-auto whitespace-pre leading-relaxed">
            <code>{expression}</code>
          </pre>
        </div>
      )}
    </div>
  );
}
