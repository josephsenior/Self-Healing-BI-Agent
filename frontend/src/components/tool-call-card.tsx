"use client";

import React, { useState } from "react";
import {
  Database,
  Table,
  BarChart2,
  GitBranch,
  Shield,
  Layers,
  Code2,
  RefreshCw,
  Eye,
  FileText,
  Globe,
  Zap,
  Search,
  Settings,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Monitor,
  CheckCircle2,
  Clock,
  Hash,
  Sigma,
  Calendar,
  FolderOpen,
  Link,
  ArrowRightLeft,
  Activity,
  List,
  Download,
} from "lucide-react";
import type { ToolCall } from "@/types";

interface ToolCallCardProps {
  toolCall: ToolCall;
}

// ─── Tool Metadata Registry ───────────────────────────────────────────────────

interface ToolMeta {
  label: string;
  icon: React.ReactNode;
  color: string;      // Tailwind text color
  bg: string;         // Tailwind bg color
  border: string;     // Tailwind border color
  badge: string;      // Tailwind badge bg
}

const TOOL_META: Record<string, ToolMeta> = {
  // Connection
  connection_operations: {
    label: "Connection",
    icon: <Link className="w-3.5 h-3.5" />,
    color: "text-blue-600",
    bg: "bg-blue-50",
    border: "border-blue-200",
    badge: "bg-blue-100 text-blue-700 border-blue-200",
  },
  // DAX Query
  dax_query_operations: {
    label: "DAX Query",
    icon: <Code2 className="w-3.5 h-3.5" />,
    color: "text-orange-600",
    bg: "bg-orange-50",
    border: "border-orange-200",
    badge: "bg-orange-100 text-orange-700 border-orange-200",
  },
  // Measure
  measure_operations: {
    label: "Measure",
    icon: <Sigma className="w-3.5 h-3.5" />,
    color: "text-violet-600",
    bg: "bg-violet-50",
    border: "border-violet-200",
    badge: "bg-violet-100 text-violet-700 border-violet-200",
  },
  // Table
  table_operations: {
    label: "Table",
    icon: <Table className="w-3.5 h-3.5" />,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    badge: "bg-emerald-100 text-emerald-700 border-emerald-200",
  },
  // Column
  column_operations: {
    label: "Column",
    icon: <Hash className="w-3.5 h-3.5" />,
    color: "text-cyan-600",
    bg: "bg-cyan-50",
    border: "border-cyan-200",
    badge: "bg-cyan-100 text-cyan-700 border-cyan-200",
  },
  // Relationship
  relationship_operations: {
    label: "Relationship",
    icon: <ArrowRightLeft className="w-3.5 h-3.5" />,
    color: "text-pink-600",
    bg: "bg-pink-50",
    border: "border-pink-200",
    badge: "bg-pink-100 text-pink-700 border-pink-200",
  },
  // Model
  model_operations: {
    label: "Model",
    icon: <Database className="w-3.5 h-3.5" />,
    color: "text-slate-600",
    bg: "bg-slate-50",
    border: "border-slate-200",
    badge: "bg-slate-100 text-slate-700 border-slate-200",
  },
  // Database
  database_operations: {
    label: "Database",
    icon: <Database className="w-3.5 h-3.5" />,
    color: "text-indigo-600",
    bg: "bg-indigo-50",
    border: "border-indigo-200",
    badge: "bg-indigo-100 text-indigo-700 border-indigo-200",
  },
  // Security Role
  security_role_operations: {
    label: "Security Role",
    icon: <Shield className="w-3.5 h-3.5" />,
    color: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
    badge: "bg-red-100 text-red-700 border-red-200",
  },
  // Hierarchy
  user_hierarchy_operations: {
    label: "Hierarchy",
    icon: <Layers className="w-3.5 h-3.5" />,
    color: "text-amber-600",
    bg: "bg-amber-50",
    border: "border-amber-200",
    badge: "bg-amber-100 text-amber-700 border-amber-200",
  },
  // Partition
  partition_operations: {
    label: "Partition",
    icon: <FolderOpen className="w-3.5 h-3.5" />,
    color: "text-teal-600",
    bg: "bg-teal-50",
    border: "border-teal-200",
    badge: "bg-teal-100 text-teal-700 border-teal-200",
  },
  // Calculation Group
  calculation_group_operations: {
    label: "Calc Group",
    icon: <BarChart2 className="w-3.5 h-3.5" />,
    color: "text-fuchsia-600",
    bg: "bg-fuchsia-50",
    border: "border-fuchsia-200",
    badge: "bg-fuchsia-100 text-fuchsia-700 border-fuchsia-200",
  },
  // Named Expression
  named_expression_operations: {
    label: "Expression",
    icon: <FileText className="w-3.5 h-3.5" />,
    color: "text-lime-700",
    bg: "bg-lime-50",
    border: "border-lime-200",
    badge: "bg-lime-100 text-lime-700 border-lime-200",
  },
  // Perspective
  perspective_operations: {
    label: "Perspective",
    icon: <Eye className="w-3.5 h-3.5" />,
    color: "text-sky-600",
    bg: "bg-sky-50",
    border: "border-sky-200",
    badge: "bg-sky-100 text-sky-700 border-sky-200",
  },
  // Culture / Translation
  culture_operations: {
    label: "Culture",
    icon: <Globe className="w-3.5 h-3.5" />,
    color: "text-rose-600",
    bg: "bg-rose-50",
    border: "border-rose-200",
    badge: "bg-rose-100 text-rose-700 border-rose-200",
  },
  object_translation_operations: {
    label: "Translation",
    icon: <Globe className="w-3.5 h-3.5" />,
    color: "text-rose-600",
    bg: "bg-rose-50",
    border: "border-rose-200",
    badge: "bg-rose-100 text-rose-700 border-rose-200",
  },
  // Calendar
  calendar_operations: {
    label: "Calendar",
    icon: <Calendar className="w-3.5 h-3.5" />,
    color: "text-orange-700",
    bg: "bg-orange-50",
    border: "border-orange-200",
    badge: "bg-orange-100 text-orange-700 border-orange-200",
  },
  // Transaction
  transaction_operations: {
    label: "Transaction",
    icon: <RefreshCw className="w-3.5 h-3.5" />,
    color: "text-zinc-600",
    bg: "bg-zinc-50",
    border: "border-zinc-200",
    badge: "bg-zinc-100 text-zinc-700 border-zinc-200",
  },
  // Trace
  trace_operations: {
    label: "Trace",
    icon: <Activity className="w-3.5 h-3.5" />,
    color: "text-purple-600",
    bg: "bg-purple-50",
    border: "border-purple-200",
    badge: "bg-purple-100 text-purple-700 border-purple-200",
  },
  // Query Group
  query_group_operations: {
    label: "Query Group",
    icon: <List className="w-3.5 h-3.5" />,
    color: "text-blue-700",
    bg: "bg-blue-50",
    border: "border-blue-200",
    badge: "bg-blue-100 text-blue-700 border-blue-200",
  },
  // Function
  function_operations: {
    label: "Function",
    icon: <Zap className="w-3.5 h-3.5" />,
    color: "text-yellow-600",
    bg: "bg-yellow-50",
    border: "border-yellow-200",
    badge: "bg-yellow-100 text-yellow-700 border-yellow-200",
  },
};

const DEFAULT_META: ToolMeta = {
  label: "Tool",
  icon: <Settings className="w-3.5 h-3.5" />,
  color: "text-zinc-600",
  bg: "bg-zinc-50",
  border: "border-zinc-200",
  badge: "bg-zinc-100 text-zinc-700 border-zinc-200",
};

function getToolMeta(name: string): ToolMeta {
  return TOOL_META[name] ?? DEFAULT_META;
}

// ─── Parse operation name from args ──────────────────────────────────────────

function getOperation(args: any): string | null {
  if (!args) return null;
  return args?.request?.operation ?? args?.operation ?? null;
}

// ─── Status Badge ─────────────────────────────────────────────────────────────

function StatusBadge({ toolCall }: { toolCall: ToolCall }) {
  if (!toolCall.result && !toolCall.error) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-zinc-600 bg-zinc-100 px-2 py-0.5 rounded-full border border-zinc-200 font-medium">
        <span className="w-1.5 h-1.5 rounded-full bg-zinc-400 animate-pulse inline-block" />
        Running
      </span>
    );
  }
  if (toolCall.error) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-red-600 bg-red-50 px-2 py-0.5 rounded-full border border-red-200 font-medium">
        <AlertTriangle className="w-2.5 h-2.5" />
        Failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-green-700 bg-green-50 px-2 py-0.5 rounded-full border border-green-200 font-medium">
      <CheckCircle2 className="w-2.5 h-2.5" />
      Done
    </span>
  );
}

// ─── JSON safe parse ──────────────────────────────────────────────────────────

function tryParseJson(str?: string) {
  if (!str) return null;
  try { return JSON.parse(str); } catch { return null; }
}

// ─── Rich Renderers ────────────────────────────────────────────────────────────

/** DAX Query → scrollable result table with CSV Export */
function DaxQueryGrid({ data }: { data: any[] }) {
  if (!Array.isArray(data) || data.length === 0)
    return <p className="text-zinc-400 italic text-xs py-1">Empty dataset returned.</p>;

  const columns = Object.keys(data[0]);

  const exportToCSV = () => {
    const headers = columns.join(",");
    const rows = data.map(row => 
      columns.map(col => {
        let val = row[col];
        if (typeof val === "object" && val !== null) {
          val = JSON.stringify(val);
        }
        const cell = val === null || val === undefined ? "" : String(val);
        // Escape quotes for CSV compliance
        const escaped = cell.replace(/"/g, '""');
        return `"${escaped}"`;
      }).join(",")
    );
    const csvContent = "\uFEFF" + [headers, ...rows].join("\r\n"); // UTF-8 BOM for Excel
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `query_result_${new Date().toISOString().slice(0, 19).replace(/[-:]/g, "")}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="mt-2">
      <div className="flex justify-between items-center mb-1.5 px-1">
        <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider font-sans">
          Query Results ({data.length} rows)
        </span>
        <button
          onClick={exportToCSV}
          className="flex items-center gap-1 text-zinc-500 hover:text-zinc-800 transition-colors text-[10px] font-sans py-0.5 px-2 rounded hover:bg-zinc-100 border border-zinc-200 bg-zinc-50 shadow-sm"
        >
          <Download className="w-3 h-3 text-zinc-500" />
          <span>Export CSV</span>
        </button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-zinc-200 max-h-64 shadow-sm">
        <table className="min-w-full divide-y divide-zinc-200 text-xs text-left">
          <thead className="sticky top-0 bg-zinc-50 border-b border-zinc-200 z-10">
            <tr>
              {columns.map((col) => (
                <th key={col} className="px-3 py-2 font-semibold text-zinc-800 border-r border-zinc-200 last:border-r-0 whitespace-nowrap font-sans">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-zinc-100">
            {data.map((row, i) => (
              <tr key={i} className="hover:bg-zinc-50/60 transition-colors">
                {columns.map((col) => {
                  const val = row[col];
                  const disp = typeof val === "object" && val !== null ? JSON.stringify(val) : String(val ?? "");
                  return (
                    <td key={col} className="px-3 py-1.5 font-mono text-[11px] border-r border-zinc-100 last:border-r-0 whitespace-nowrap text-zinc-800">
                      {disp}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** DAX expression code block */
function DaxCodeBlock({ expression }: { expression: string }) {
  return (
    <pre className="bg-zinc-950 text-orange-300 p-3 rounded-lg border border-zinc-800 font-mono text-[11px] overflow-x-auto whitespace-pre leading-relaxed mt-2">
      <code>{expression}</code>
    </pre>
  );
}

/** Measure create/update card */
function MeasureCard({ args }: { args: any }) {
  const req = args?.request ?? args ?? {};
  const name = req.name ?? req.measureName ?? "";
  const table = req.tableName ?? "";
  const expression = req.expression ?? "";
  const description = req.description ?? "";
  const format = req.formatString ?? "";

  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50/30 p-3 mt-2 space-y-2">
      <div className="flex flex-wrap gap-4 text-xs border-b border-violet-200/60 pb-2">
        {table && (
          <div>
            <span className="text-violet-500 text-[10px] uppercase tracking-wider font-semibold mr-1">Table</span>
            <span className="font-mono text-zinc-900 font-bold">{table}</span>
          </div>
        )}
        {name && (
          <div>
            <span className="text-violet-500 text-[10px] uppercase tracking-wider font-semibold mr-1">Measure</span>
            <span className="font-mono text-violet-700 font-bold">[{name}]</span>
          </div>
        )}
        {format && (
          <div>
            <span className="text-violet-500 text-[10px] uppercase tracking-wider font-semibold mr-1">Format</span>
            <span className="font-mono text-zinc-700">{format}</span>
          </div>
        )}
      </div>
      {description && <p className="text-xs text-zinc-600 italic">{description}</p>}
      {expression && (
        <>
          <p className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">DAX Expression</p>
          <DaxCodeBlock expression={expression} />
        </>
      )}
    </div>
  );
}

/** Connection list — local PBI instances */
function LocalInstancesList({ data }: { data: any[] }) {
  if (!Array.isArray(data) || data.length === 0)
    return <p className="text-zinc-400 italic text-xs py-1">No active local instances found.</p>;

  return (
    <div className="space-y-2 mt-2">
      {data.map((inst, i) => (
        <div key={i} className="flex items-center justify-between px-3 py-2.5 rounded-lg border border-blue-200 bg-white shadow-sm hover:bg-blue-50/20 transition-colors">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center">
              <Monitor className="w-3.5 h-3.5 text-blue-600" />
            </div>
            <div>
              <p className="font-semibold text-zinc-900 text-xs">{inst.connectionName ?? inst.serverName ?? "Power BI Desktop"}</p>
              {inst.port && <p className="text-[10px] text-zinc-500 font-mono">Port {inst.port}</p>}
            </div>
          </div>
          <span className="text-[9px] font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded-full border border-green-200">
            Available
          </span>
        </div>
      ))}
    </div>
  );
}

/** Column / table listing result */
function SchemaList({ data, kind }: { data: any[]; kind: "column" | "table" | "generic" }) {
  if (!Array.isArray(data) || data.length === 0)
    return <p className="text-zinc-400 italic text-xs py-1">No items returned.</p>;

  const nameKey = kind === "column" ? "name" : kind === "table" ? "name" : "name";

  return (
    <div className="mt-2 rounded-lg border border-zinc-200 overflow-hidden">
      <div className="max-h-52 overflow-y-auto divide-y divide-zinc-100 bg-white">
        {data.map((item, i) => (
          <div key={i} className="flex items-center justify-between px-3 py-1.5 hover:bg-zinc-50 transition-colors">
            <span className="font-mono text-[11px] text-zinc-800">{item[nameKey] ?? JSON.stringify(item)}</span>
            {item.dataType && (
              <span className="text-[9px] text-zinc-500 bg-zinc-100 px-1.5 py-0.5 rounded font-mono border border-zinc-200">
                {item.dataType}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Relationship visualization */
function RelationshipCard({ data }: { data: any[] | any }) {
  const items = Array.isArray(data) ? data : [data];
  if (!items.length) return null;

  return (
    <div className="mt-2 space-y-2">
      {items.map((rel, i) => (
        <div key={i} className="rounded-lg border border-pink-200 bg-white p-3 text-xs shadow-sm">
          <div className="flex items-center gap-2 text-zinc-800">
            <span className="font-mono font-semibold text-zinc-900">{rel.fromTable ?? "?"}</span>
            <span className="text-[10px] text-zinc-400 font-mono">[{rel.fromColumn ?? "?"}]</span>
            <ArrowRightLeft className="w-3 h-3 text-pink-500 flex-shrink-0" />
            <span className="font-mono font-semibold text-zinc-900">{rel.toTable ?? "?"}</span>
            <span className="text-[10px] text-zinc-400 font-mono">[{rel.toColumn ?? "?"}]</span>
          </div>
          {rel.cardinality && (
            <div className="mt-1 text-[10px] text-zinc-500">
              <span className="font-semibold">Cardinality:</span> {rel.cardinality}
              {rel.crossFilteringBehavior && <span className="ml-3"><span className="font-semibold">Cross-filter:</span> {rel.crossFilteringBehavior}</span>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/** Generic key-value property display */
function PropertiesCard({ data }: { data: Record<string, any> }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (!entries.length) return null;

  return (
    <div className="mt-2 rounded-lg border border-zinc-200 divide-y divide-zinc-100 overflow-hidden bg-white shadow-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-baseline justify-between px-3 py-1.5 hover:bg-zinc-50 transition-colors">
          <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider">{k}</span>
          <span className="font-mono text-[11px] text-zinc-800 max-w-[200px] truncate">{String(v)}</span>
        </div>
      ))}
    </div>
  );
}

/** Running indicator dots */
function RunningIndicator({ meta }: { meta: ToolMeta }) {
  return (
    <div className={`flex items-center gap-1.5 mt-1.5 px-2 py-1 rounded-md ${meta.bg} border ${meta.border}`}>
      <Clock className={`w-3 h-3 ${meta.color} animate-spin`} style={{ animationDuration: "2s" }} />
      <span className={`text-[10px] font-medium ${meta.color}`}>Executing…</span>
    </div>
  );
}

// ─── Rich Result Renderer (per tool) ─────────────────────────────────────────

function RichResult({ toolCall }: { toolCall: ToolCall }) {
  const { name, arguments: args, result } = toolCall;
  const parsedResult = tryParseJson(result);
  const op = getOperation(args);

  // DAX Query → table grid
  if (name === "dax_query_operations" && Array.isArray(parsedResult)) {
    return <DaxQueryGrid data={parsedResult} />;
  }

  // Connection list
  if (name === "connection_operations" && (op === "ListLocalInstances" || op === "ListConnections") && Array.isArray(parsedResult)) {
    return <LocalInstancesList data={parsedResult} />;
  }

  // Connection → connect confirmation
  if (name === "connection_operations" && op === "Connect") {
    const obj = parsedResult && typeof parsedResult === "object" ? parsedResult : null;
    return obj ? <PropertiesCard data={obj} /> : null;
  }

  // Measure create/update
  if (name === "measure_operations" && (op === "CreateMeasure" || op === "UpdateMeasure" || op === "GetMeasure")) {
    return <MeasureCard args={args} />;
  }

  // Measure list
  if (name === "measure_operations" && op === "GetAllMeasures" && Array.isArray(parsedResult)) {
    return <SchemaList data={parsedResult} kind="generic" />;
  }

  // Table list
  if (name === "table_operations" && op === "GetAllTables" && Array.isArray(parsedResult)) {
    return <SchemaList data={parsedResult} kind="table" />;
  }

  // Column list
  if (name === "column_operations" && op === "GetAllColumns" && Array.isArray(parsedResult)) {
    return <SchemaList data={parsedResult} kind="column" />;
  }

  // Relationship list/details
  if (name === "relationship_operations") {
    if (Array.isArray(parsedResult)) return <RelationshipCard data={parsedResult} />;
    if (parsedResult && typeof parsedResult === "object") return <RelationshipCard data={[parsedResult]} />;
  }

  // Generic object result → properties card
  if (parsedResult && typeof parsedResult === "object" && !Array.isArray(parsedResult)) {
    return <PropertiesCard data={parsedResult} />;
  }

  // Generic array result → schema list
  if (Array.isArray(parsedResult) && parsedResult.length > 0) {
    return <SchemaList data={parsedResult} kind="generic" />;
  }

  // Plain string result (success confirmation etc.)
  if (result && !parsedResult) {
    return (
      <p className="text-xs text-zinc-700 mt-1 px-1 py-0.5 font-mono leading-relaxed">{result}</p>
    );
  }

  return null;
}

// ─── Main ToolCallCard Component ──────────────────────────────────────────────

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const meta = getToolMeta(toolCall.name);
  const op = getOperation(toolCall.arguments);

  const hasRichResult = !!(toolCall.result || toolCall.error);
  const isRunning = !toolCall.result && !toolCall.error;

  // Human-friendly label: "Measure › CreateMeasure"
  const displayLabel = op ? `${meta.label} › ${op}` : meta.label;

  return (
    <div className={`rounded-xl border ${meta.border} bg-white shadow-sm overflow-hidden animate-fade-in`}>
      {/* Colored top strip */}
      <div className={`h-0.5 ${meta.bg.replace("bg-", "bg-").replace("-50", "-400").replace("bg-zinc-400", "bg-zinc-300")}`} />

      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className={`flex items-center justify-center w-6 h-6 rounded-lg ${meta.bg} ${meta.color} border ${meta.border} flex-shrink-0`}>
            {meta.icon}
          </span>
          <div>
            <span className="text-[11px] font-semibold text-zinc-800 font-mono">{displayLabel}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <StatusBadge toolCall={toolCall} />
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1 rounded hover:bg-zinc-100 text-zinc-400 hover:text-zinc-600 transition-colors"
            aria-label="Toggle details"
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Running indicator */}
      {isRunning && (
        <div className="px-3 pb-2.5">
          <RunningIndicator meta={meta} />
        </div>
      )}

      {/* Rich result */}
      {hasRichResult && !toolCall.error && (
        <div className="px-3 pb-3">
          <RichResult toolCall={toolCall} />
        </div>
      )}

      {/* Error */}
      {toolCall.error && (
        <div className="px-3 pb-3">
          <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 mt-1">
            <p className="text-[10px] font-semibold text-red-500 uppercase tracking-wider mb-1">Error</p>
            <pre className="text-xs text-red-700 whitespace-pre-wrap font-mono overflow-x-auto">{toolCall.error}</pre>
          </div>
        </div>
      )}

      {/* Expanded raw args */}
      {expanded && (
        <div className="border-t border-zinc-100 bg-zinc-50 px-3 py-2.5 space-y-2">
          <p className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">Arguments</p>
          <pre className="text-[11px] text-zinc-700 font-mono whitespace-pre-wrap overflow-x-auto leading-relaxed">
            {JSON.stringify(toolCall.arguments, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
