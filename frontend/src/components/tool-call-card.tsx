"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  ArrowRightLeft,
  BarChart2,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  Clock3,
  Cloud,
  Code2,
  Copy,
  Database,
  Download,
  ExternalLink,
  FileCode2,
  FileText,
  FolderOpen,
  Globe2,
  History,
  Image as ImageIcon,
  Layers3,
  Monitor,
  RefreshCw,
  Rocket,
  Search,
  Settings2,
  ShieldCheck,
  Sigma,
  Sparkles,
  Table2,
  TerminalSquare,
  X,
  XCircle,
} from "lucide-react";
import type { ToolCall } from "@/types";

type JsonRecord = Record<string, unknown>;
type ToolKind =
  | "query"
  | "code"
  | "connection"
  | "model"
  | "validation"
  | "workspace"
  | "desktop"
  | "publish"
  | "render"
  | "review"
  | "generic";

interface ToolTheme {
  label: string;
  icon: React.ReactNode;
  kind: ToolKind;
  accent: string;
  iconClass: string;
  softClass: string;
  borderClass: string;
}

interface ToolCallCardProps {
  toolCall: ToolCall;
  apiBase?: string;
}

const THEMES: Record<ToolKind, Omit<ToolTheme, "label" | "icon">> = {
  query: { kind: "query", accent: "#f97316", iconClass: "text-orange-700", softClass: "bg-orange-50", borderClass: "border-orange-200" },
  code: { kind: "code", accent: "#18181b", iconClass: "text-zinc-700", softClass: "bg-zinc-100", borderClass: "border-zinc-300" },
  connection: { kind: "connection", accent: "#2563eb", iconClass: "text-blue-700", softClass: "bg-blue-50", borderClass: "border-blue-200" },
  model: { kind: "model", accent: "#7c3aed", iconClass: "text-violet-700", softClass: "bg-violet-50", borderClass: "border-violet-200" },
  validation: { kind: "validation", accent: "#059669", iconClass: "text-emerald-700", softClass: "bg-emerald-50", borderClass: "border-emerald-200" },
  workspace: { kind: "workspace", accent: "#4f46e5", iconClass: "text-indigo-700", softClass: "bg-indigo-50", borderClass: "border-indigo-200" },
  desktop: { kind: "desktop", accent: "#0891b2", iconClass: "text-cyan-700", softClass: "bg-cyan-50", borderClass: "border-cyan-200" },
  publish: { kind: "publish", accent: "#0284c7", iconClass: "text-sky-700", softClass: "bg-sky-50", borderClass: "border-sky-200" },
  render: { kind: "render", accent: "#db2777", iconClass: "text-pink-700", softClass: "bg-pink-50", borderClass: "border-pink-200" },
  review: { kind: "review", accent: "#9333ea", iconClass: "text-purple-700", softClass: "bg-purple-50", borderClass: "border-purple-200" },
  generic: { kind: "generic", accent: "#71717a", iconClass: "text-zinc-700", softClass: "bg-zinc-50", borderClass: "border-zinc-200" },
};

const OPERATION_TOOLS: Record<string, { label: string; icon: React.ReactNode }> = {
  dax_query_operations: { label: "DAX query", icon: <Table2 className="size-4" /> },
  measure_operations: { label: "Measure", icon: <Sigma className="size-4" /> },
  table_operations: { label: "Table", icon: <Table2 className="size-4" /> },
  column_operations: { label: "Column", icon: <Layers3 className="size-4" /> },
  relationship_operations: { label: "Relationship", icon: <ArrowRightLeft className="size-4" /> },
  model_operations: { label: "Semantic model", icon: <Database className="size-4" /> },
  database_operations: { label: "Database", icon: <Database className="size-4" /> },
  security_role_operations: { label: "Security role", icon: <ShieldCheck className="size-4" /> },
  user_hierarchy_operations: { label: "Hierarchy", icon: <Layers3 className="size-4" /> },
  partition_operations: { label: "Partition", icon: <FolderOpen className="size-4" /> },
  calculation_group_operations: { label: "Calculation group", icon: <BarChart2 className="size-4" /> },
  named_expression_operations: { label: "Named expression", icon: <FileCode2 className="size-4" /> },
  perspective_operations: { label: "Perspective", icon: <Search className="size-4" /> },
  culture_operations: { label: "Culture", icon: <Globe2 className="size-4" /> },
  object_translation_operations: { label: "Translation", icon: <Globe2 className="size-4" /> },
  calendar_operations: { label: "Calendar", icon: <Table2 className="size-4" /> },
  transaction_operations: { label: "Transaction", icon: <RefreshCw className="size-4" /> },
  trace_operations: { label: "Trace", icon: <Activity className="size-4" /> },
  query_group_operations: { label: "Query group", icon: <Layers3 className="size-4" /> },
  function_operations: { label: "Function", icon: <Code2 className="size-4" /> },
};

function titleCase(value: string) {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function asRecord(value: unknown): JsonRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : null;
}

function parseResult(result?: string): unknown {
  if (!result) return null;
  try { return JSON.parse(result); } catch { return result; }
}

function getOperation(args: JsonRecord): string | null {
  const request = asRecord(args.request);
  const operation = request?.operation ?? args.operation;
  return typeof operation === "string" ? operation : null;
}

function classifyTool(name: string): ToolKind {
  if (name === "dax_query_operations" || name === "bigquery_query") return "query";
  if (name === "format_dax" || name === "run_python_sandbox") return "code";
  if (name === "connection_operations") return "connection";
  if (["bigquery_list_tables", "bigquery_get_table_schema", "bigquery_semantic_catalog", "bigquery_create_powerbi_semantic_model"].includes(name)) return "model";
  if (OPERATION_TOOLS[name]) return "model";
  if (name.includes("validate") || name.includes("quality") || name.includes("readiness") || name === "audit_active_dashboard") return "validation";
  if (name.includes("dashboard") || name === "stage_pbir_report" || name === "inspect_pbir_report" || name === "preview_pbir_report") return "workspace";
  if (name.includes("desktop")) return "desktop";
  if (name.includes("publish") || name.includes("fabric")) return "publish";
  if (name === "render_powerbi_report") return "render";
  if (name.includes("review") || name.includes("visual_qa")) return "review";
  return "generic";
}

function getTheme(name: string): ToolTheme {
  const kind = classifyTool(name);
  const base = THEMES[kind];
  if (OPERATION_TOOLS[name]) return { ...base, ...OPERATION_TOOLS[name] };
  const definitions: Record<string, { label: string; icon: React.ReactNode }> = {
    connection_operations: { label: "Power BI connection", icon: <Database className="size-4" /> },
    format_dax: { label: "DAX formatter", icon: <Code2 className="size-4" /> },
    run_python_sandbox: { label: "Python sandbox", icon: <TerminalSquare className="size-4" /> },
    validate_dashboard_spec: { label: "Layout validation", icon: <ShieldCheck className="size-4" /> },
    validate_dashboard_semantics: { label: "Semantic validation", icon: <ShieldCheck className="size-4" /> },
    evaluate_dashboard_quality: { label: "Quality review", icon: <Sparkles className="size-4" /> },
    validate_pbir_report: { label: "PBIR validation", icon: <ShieldCheck className="size-4" /> },
    validate_pbir_official_schemas: { label: "Schema validation", icon: <ShieldCheck className="size-4" /> },
    check_powerbi_cloud_qa_readiness: { label: "Cloud readiness", icon: <Cloud className="size-4" /> },
    stage_pbir_report: { label: "Build PBIR report", icon: <FileCode2 className="size-4" /> },
    inspect_pbir_report: { label: "Inspect report", icon: <Search className="size-4" /> },
    preview_pbir_report: { label: "Report preview", icon: <BarChart2 className="size-4" /> },
    create_dashboard_workspace: { label: "Create dashboard", icon: <BarChart2 className="size-4" /> },
    get_active_dashboard: { label: "Active dashboard", icon: <BarChart2 className="size-4" /> },
    set_active_dashboard: { label: "Switch dashboard", icon: <ArrowRight className="size-4" /> },
    revise_active_dashboard: { label: "Revise dashboard", icon: <RefreshCw className="size-4" /> },
    list_dashboard_versions: { label: "Version history", icon: <History className="size-4" /> },
    rollback_dashboard: { label: "Restore version", icon: <History className="size-4" /> },
    audit_active_dashboard: { label: "Dashboard audit", icon: <ShieldCheck className="size-4" /> },
    prepare_pbir_for_powerbi_desktop: { label: "Prepare for Desktop", icon: <Monitor className="size-4" /> },
    open_pbir_in_powerbi_desktop: { label: "Open in Desktop", icon: <Monitor className="size-4" /> },
    open_active_dashboard_in_powerbi_desktop: { label: "Open dashboard", icon: <Monitor className="size-4" /> },
    publish_pbir_to_fabric: { label: "Publish to Fabric", icon: <Rocket className="size-4" /> },
    render_powerbi_report: { label: "Render report", icon: <ImageIcon className="size-4" /> },
    review_powerbi_render: { label: "Visual review", icon: <Sparkles className="size-4" /> },
    decide_powerbi_visual_qa_iteration: { label: "QA decision", icon: <RefreshCw className="size-4" /> },
    bigquery_list_tables: { label: "Discover BigQuery tables", icon: <Database className="size-4" /> },
    bigquery_get_table_schema: { label: "Inspect BigQuery schema", icon: <Table2 className="size-4" /> },
    bigquery_query: { label: "Analyze BigQuery data", icon: <Sigma className="size-4" /> },
    bigquery_semantic_catalog: { label: "Build semantic catalog", icon: <Layers3 className="size-4" /> },
    bigquery_create_powerbi_semantic_model: { label: "Create Power BI model", icon: <Database className="size-4" /> },
    list_powerbi_visual_capabilities: { label: "Select Power BI visuals", icon: <BarChart2 className="size-4" /> },
  };
  return { ...base, ...(definitions[name] ?? { label: titleCase(name), icon: <Settings2 className="size-4" /> }) };
}

function getActionSummary(toolCall: ToolCall, data: unknown): string {
  const op = getOperation(toolCall.arguments);
  if (op) return titleCase(op);
  const args = toolCall.arguments;
  const result = asRecord(data);
  const complete = toolCall.status === "complete" || toolCall.result !== undefined;
  if (toolCall.status === "failed" || toolCall.error) {
    return `Could not complete: ${getTheme(toolCall.name).label.toLowerCase()}`;
  }
  const table = String(args.table ?? result?.table ?? "the selected table");
  if (toolCall.name === "bigquery_list_tables") {
    const tables = Array.isArray(result?.tables) ? result.tables : [];
    return complete ? `Found ${tables.length} table${tables.length === 1 ? "" : "s"} in ${String(args.dataset ?? "the dataset")}` : `Discovering tables in ${String(args.dataset ?? "the dataset")}`;
  }
  if (toolCall.name === "bigquery_get_table_schema") {
    const fields = Array.isArray(result?.fields) ? result.fields : [];
    return complete ? `Mapped ${fields.length} columns from ${table}` : `Reading columns and data types from ${table}`;
  }
  if (toolCall.name === "bigquery_query") {
    const sql = String(args.sql ?? "").toLowerCase();
    const dimensions = ["country", "product", "channel"].filter((name) => sql.includes(name));
    const intent = sql.includes("date_trunc") || sql.includes("extract(month")
      ? "Calculating the monthly performance trend"
      : dimensions.length
        ? `Comparing performance by ${dimensions.join(" and ")}`
        : "Calculating headline business metrics";
    return complete ? `${intent} · ${Number(result?.row_count ?? 0)} rows returned` : intent;
  }
  if (toolCall.name === "bigquery_semantic_catalog") return complete ? `Catalogued fields from ${table} for report authoring` : `Preparing report-safe fields from ${table}`;
  if (toolCall.name === "bigquery_create_powerbi_semantic_model") return complete ? `Power BI ${String(result?.storage_mode ?? args.storage_mode ?? "")} model created from ${table}` : `Creating a ${String(args.storage_mode ?? "directQuery")} model from ${table}`;
  if (toolCall.name === "list_powerbi_visual_capabilities") return complete ? "Matched the plan to supported Power BI visuals" : "Checking supported visuals and their field roles";
  if (toolCall.name === "validate_dashboard_spec") return complete ? "Checked page layout, sizing, and visual placement" : "Checking page layout, sizing, and visual placement";
  if (toolCall.name === "validate_dashboard_semantics") return complete ? "Checked every visual field against the current model" : "Verifying visual fields against the current model";
  if (toolCall.name === "evaluate_dashboard_quality") return complete ? "Reviewed dashboard density and readability" : "Reviewing dashboard density and readability";
  if (toolCall.name === "create_dashboard_workspace") return complete ? `Created ${String(result?.dashboard_id ?? args.dashboard_id ?? "the dashboard")}` : `Building and validating ${String(args.dashboard_id ?? "the dashboard")}`;
  if (toolCall.name === "audit_active_dashboard") return complete ? "Audited the active report and collected findings" : "Auditing the active report for layout and model issues";
  if (toolCall.name === "revise_active_dashboard") return complete ? `Saved a validated revision${result?.version ? ` as version ${String(result.version)}` : ""}` : `Applying a validated revision: ${String(args.reason ?? "requested improvements")}`;
  const candidate = args.display_name ?? args.dashboard_id ?? args.project_path ?? result?.dashboard_id ?? result?.display_name;
  if (typeof candidate === "string" && candidate) return candidate;
  if (toolCall.name === "run_python_sandbox") return "Execute analysis code";
  if (toolCall.name === "format_dax") return "Format expression";
  return complete ? `Finished ${getTheme(toolCall.name).label.toLowerCase()}` : `Working on ${getTheme(toolCall.name).label.toLowerCase()}`;
}

function formatDuration(ms: number) {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

function Status({ toolCall, durationMs }: { toolCall: ToolCall; durationMs?: number }) {
  const pill = (cls: string, icon: React.ReactNode, label: string) => (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${cls}`}>
      {icon}{label}{durationMs !== undefined && !(toolCall.status === "running" || toolCall.status === undefined) ? <span className="font-mono font-semibold normal-case tracking-normal opacity-80">· {formatDuration(durationMs)}</span> : null}
    </span>
  );
  if (toolCall.status === "cancelled") return pill("bg-amber-100 text-amber-700", <XCircle className="size-3" />, "Interrupted");
  if (toolCall.status === "failed" || toolCall.error) return pill("bg-red-100 text-red-700", <XCircle className="size-3" />, "Failed");
  if (toolCall.status === "complete" || toolCall.result !== undefined) return pill("bg-emerald-100 text-emerald-700", <CheckCircle2 className="size-3" />, "Complete");
  return pill("bg-zinc-100 text-zinc-600", <Clock3 className="size-3 animate-spin" />, "Running");
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };
  return (
    <button onClick={copy} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium text-zinc-500 hover:bg-white/10 hover:text-white" aria-label="Copy code">
      {copied ? <Check className="size-3" /> : <Copy className="size-3" />}{copied ? "Copied" : "Copy"}
    </button>
  );
}

function CodePanel({ code, language, output }: { code: string; language: string; output?: string }) {
  return (
    <div className="overflow-hidden rounded-xl bg-zinc-950 text-zinc-200 shadow-inner">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">{language}</span>
        <CopyButton value={code} />
      </div>
      <pre className="max-h-64 overflow-auto p-3 text-[11px] leading-relaxed"><code>{code}</code></pre>
      {output && (
        <div className="border-t border-white/10 bg-black/30 p-3">
          <p className="mb-1.5 text-[9px] font-bold uppercase tracking-[0.16em] text-zinc-600">Output</p>
          <pre className="max-h-44 overflow-auto whitespace-pre-wrap text-[11px] text-emerald-300">{output}</pre>
        </div>
      )}
    </div>
  );
}

function DataGrid({ rows }: { rows: unknown[] }) {
  const records = rows.filter((row): row is JsonRecord => asRecord(row) !== null);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [limit, setLimit] = useState(50);
  if (!records.length) return <EmptyState label="No rows returned" />;
  const columns = Array.from(new Set(records.slice(0, 50).flatMap((row) => Object.keys(row))));

  const sorted = [...records];
  if (sortKey) {
    sorted.sort((a, b) => {
      const av = a[sortKey]; const bv = b[sortKey];
      const an = typeof av === "number"; const bn = typeof bv === "number";
      if (an && bn) return sortDir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number);
      const as = String(av ?? ""); const bs = String(bv ?? "");
      return sortDir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
  }
  const page = sorted.slice(0, limit);
  const isNumeric = (key: string) => records.every((r) => typeof r[key] === "number");

  const exportCsv = () => {
    const escape = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
    const csv = [columns.join(","), ...records.map((row) => columns.map((key) => escape(row[key])).join(","))].join("\r\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `query-${Date.now()}.csv`; anchor.click(); URL.revokeObjectURL(url);
  };
  const copyJson = async () => {
    await navigator.clipboard.writeText(JSON.stringify(records, null, 2));
    setCopiedJson(true);
    window.setTimeout(() => setCopiedJson(false), 1200);
  };
  const [copiedJson, setCopiedJson] = useState(false);

  return (
    <div className="overflow-hidden rounded-xl border border-orange-200 bg-white">
      <div className="flex flex-wrap items-center gap-2 bg-orange-50/70 px-3 py-2">
        <span className="text-[10px] font-bold uppercase tracking-wider text-orange-800">{records.length.toLocaleString()} rows · {columns.length} columns</span>
        <div className="ml-auto flex items-center gap-1">
          <button onClick={copyJson} className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 text-[10px] font-semibold text-zinc-600 shadow-sm ring-1 ring-zinc-200 hover:bg-zinc-50" aria-label="Copy JSON"><Copy className="size-3" />{copiedJson ? "Copied" : "JSON"}</button>
          <button onClick={exportCsv} className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 text-[10px] font-semibold text-orange-700 shadow-sm ring-1 ring-orange-200 hover:bg-orange-100"><Download className="size-3" /> CSV</button>
        </div>
      </div>
      <div className="max-h-72 overflow-auto">
        <table className="min-w-full border-collapse text-left text-[11px]">
          <thead className="sticky top-0 z-10 bg-zinc-50 text-zinc-600 shadow-[0_1px_0_#e4e4e7]">
            <tr>{columns.map((column) => {
              const active = sortKey === column;
              return <th key={column} className="whitespace-nowrap px-3 py-2 font-semibold">
                <button onClick={() => {
                  if (active) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
                  else { setSortKey(column); setSortDir("asc"); }
                }} className="inline-flex items-center gap-1 hover:text-orange-700" aria-label={`Sort by ${column}`}>
                  {column}{active ? (sortDir === "asc" ? " ↑" : " ↓") : " ⇅"}
                </button>
              </th>;
            })}</tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {page.map((row, index) => <tr key={index} className="hover:bg-orange-50/40">{columns.map((column) => <td key={column} className={`max-w-64 truncate whitespace-nowrap px-3 py-1.5 font-mono ${isNumeric(column) ? "text-right" : ""} ${row[column] === null || row[column] === undefined ? "text-zinc-400" : "text-zinc-700"}`}>{formatValue(row[column])}</td>)}</tr>)}
          </tbody>
        </table>
      </div>
      {records.length > limit && (
        <button onClick={() => setLimit((l) => l + 100)} className="w-full border-t border-zinc-100 bg-zinc-50/60 py-1.5 text-[10px] font-semibold text-zinc-500 hover:bg-zinc-100">
          Show {Math.min(100, records.length - limit).toLocaleString()} more rows ({records.length.toLocaleString()} total)
        </button>
      )}
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function EmptyState({ label }: { label: string }) {
  return <div className="flex items-center gap-2 rounded-lg border border-dashed border-zinc-200 px-3 py-4 text-xs text-zinc-400"><Circle className="size-3" />{label}</div>;
}

function ValidationPanel({ data }: { data: unknown }) {
  const record = asRecord(data);
  if (!record) return <ValuePanel data={data} />;
  const passed = record.valid === true || record.ready === true || record.accepted === true;
  const gates = Array.isArray(record.gates) ? record.gates : null;
  const checks = asRecord(record.checks) ?? asRecord(record.gates_summary);
  const issues = [record.issues, record.layout_errors, record.layout_issues, record.quality_issues, record.semantic_issues]
    .flatMap((item) => Array.isArray(item) ? item : [])
    .filter(Boolean);
  const gateStatus = (value: unknown): "ok" | "warn" | "fail" => {
    if (value === true || value === "passed" || value === "passed_with_findings" || value === "PASSED") return "ok";
    if (value === false || value === "failed" || value === "FAILED" || value === "blocked" || value === "BLOCKED") return "fail";
    if (value === "unavailable" || value === "skipped") return "warn";
    return "ok";
  };
  const statusIcon = (status: "ok" | "warn" | "fail") =>
    status === "ok" ? <Check className="size-2.5" /> : status === "fail" ? <XCircle className="size-2.5" /> : <AlertCircle className="size-2.5" />;
  const statusCls = (status: "ok" | "warn" | "fail") =>
    status === "ok" ? "bg-emerald-100 text-emerald-700" : status === "fail" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700";
  return (
    <div className="space-y-2.5">
      <div className={`flex items-center gap-3 rounded-xl border p-3 ${passed ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
        <span className={`grid size-8 place-items-center rounded-full ${passed ? "bg-emerald-600 text-white" : "bg-amber-500 text-white"}`}>{passed ? <Check className="size-4" /> : <AlertCircle className="size-4" />}</span>
        <div><p className="text-xs font-bold text-zinc-900">{passed ? "All checks passed" : `${issues.length || "Some"} checks need attention`}</p><p className="text-[10px] text-zinc-500">{passed ? "This artifact is ready for the next step." : "Review the findings below before continuing."}</p></div>
      </div>
      {gates && gates.length > 0 && (
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
          {gates.map((gate, index) => {
            const item = asRecord(gate) ?? {};
            const name = String(item.name ?? item.gate ?? item.step ?? `Gate ${index + 1}`);
            const status = gateStatus(item.status ?? item.passed);
            const detail = item.detail ? String(item.detail).slice(0, 60) : "";
            return (
              <div key={`${name}-${index}`} className={`rounded-lg border px-2.5 py-2 ${status === "ok" ? "border-emerald-200 bg-white" : status === "fail" ? "border-red-200 bg-white" : "border-amber-200 bg-white"}`}>
                <div className="flex items-center gap-2">
                  <span className={`grid size-4 place-items-center rounded-full ${statusCls(status)}`}>{statusIcon(status)}</span>
                  <span className="truncate text-[10px] font-semibold text-zinc-700">{titleCase(name)}</span>
                </div>
                {detail ? <p className="mt-0.5 truncate text-[9px] text-zinc-400" title={String(item.detail)}>{detail}</p> : null}
              </div>
            );
          })}
        </div>
      )}
      {checks && Object.keys(checks).length > 0 && !gates && <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">{Object.entries(checks).map(([key, value]) => {
        const status = gateStatus(value);
        return <div key={key} className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-2.5 py-2"><span className={`grid size-4 place-items-center rounded-full ${statusCls(status)}`}>{statusIcon(status)}</span><span className="truncate text-[10px] font-medium text-zinc-700">{titleCase(key)}</span></div>;
      })}</div>}
      {issues.length > 0 && <div className="space-y-1.5">{issues.slice(0, 12).map((issue, index) => {
        const item = asRecord(issue);
        const severity = String(item?.severity ?? "warning").toLowerCase();
        const badge = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.warning;
        const message = item?.message ?? item?.detail ?? issue;
        return <div key={index} className="flex gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2">
          <AlertCircle className={`mt-0.5 size-3 shrink-0 ${severity === "error" ? "text-red-500" : "text-amber-500"}`} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5"><span className={`rounded-full px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider ring-1 ${badge.cls}`}>{badge.label}</span>{item?.code ? <span className="font-mono text-[9px] text-zinc-400">{String(item.code)}</span> : null}</div>
            <p className="mt-0.5 text-[11px] leading-relaxed text-zinc-700">{formatValue(message)}</p>
            {item?.page ? <p className="mt-0.5 text-[9px] font-semibold uppercase text-zinc-400">Page: {String(item.page)}</p> : null}
          </div>
        </div>;
      })}</div>}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2"><p className="text-[9px] font-bold uppercase tracking-wider text-zinc-400">{label}</p><div className="mt-0.5 truncate text-sm font-bold text-zinc-800">{value}</div></div>;
}

function DashboardPanel({ data, images, apiBase }: { data: unknown; images?: string[]; apiBase?: string }) {
  const root = asRecord(data);
  if (!root) return <ValuePanel data={data} />;
  const dashboard = asRecord(root.dashboard) ?? root;
  const current = asRecord(root.current) ?? root;
  const spec = asRecord(current.spec) ?? asRecord(root.spec);
  const preview = asRecord(current.preview) ?? asRecord(root.preview);
  const pages = Array.isArray(spec?.pages) ? spec.pages : Array.isArray(preview?.pages) ? preview.pages : Array.isArray(root.pages) ? root.pages : [];
  const visualCount = pages.reduce((count, page) => count + (Array.isArray(asRecord(page)?.visuals) ? (asRecord(page)?.visuals as unknown[]).length : 0), 0);
  const title = spec?.title ?? dashboard.title ?? root.display_name ?? root.dashboard_id;
  const path = current.pbir_path ?? current.report_path ?? root.pbir_path ?? root.report_path ?? root.project_path;
  const qa = asRecord(root.qa);
  const accepted = root.accepted === true;
  const qaStatus = qa ? String(qa.status ?? qa.outcome ?? "") : "";
  const qaPromotable = qa?.promotable === true;
  const qaScore = typeof qa?.score === "number" ? qa.score : undefined;
  const qaBadge = qaStatus
    ? { label: qaStatus, cls: qaPromotable || qaStatus === "VERIFIED" || qaStatus === "VERIFIED_WITH_WARNINGS" ? "bg-emerald-100 text-emerald-700 ring-emerald-200" : "bg-amber-100 text-amber-700 ring-amber-200" }
    : accepted
      ? { label: "Accepted", cls: "bg-emerald-100 text-emerald-700 ring-emerald-200" }
      : null;
  return (
    <div className="overflow-hidden rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white">
      <div className="flex items-start gap-3 p-3.5">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-indigo-600 text-white shadow-sm"><BarChart2 className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <p className="truncate text-sm font-bold text-zinc-900">{formatValue(title ?? "Power BI report")}</p>
            {qaBadge && <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ring-1 ${qaBadge.cls}`}>{qaBadge.label}</span>}
            {qaScore !== undefined && <span className="rounded-full bg-white px-2 py-0.5 font-mono text-[9px] font-bold text-zinc-600 ring-1 ring-zinc-200">QA {qaScore}</span>}
          </div>
          <p className="mt-0.5 truncate text-[10px] text-zinc-500">{formatValue(path ?? "Dashboard workspace")}</p>
        </div>
        {dashboard.active_version ?? current.version ?? root.version ? <span className="rounded-full bg-indigo-100 px-2 py-1 text-[10px] font-bold text-indigo-700">v{String(dashboard.active_version ?? current.version ?? root.version)}</span> : null}
      </div>
      <div className="grid grid-cols-3 gap-1.5 border-t border-indigo-100 bg-white/60 p-2.5">
        <Stat label="Pages" value={pages.length || "—"} /><Stat label="Visuals" value={visualCount || "—"} /><Stat label="Issues" value={(Array.isArray(current.quality_issues) ? current.quality_issues.length : 0) + (Array.isArray(current.semantic_issues) ? current.semantic_issues.length : 0)} />
      </div>
      {images && images.length > 0 && (
        <div className="border-t border-indigo-100 bg-white/70 p-3">
          <ImageGallery images={images} apiBase={apiBase} />
        </div>
      )}
      {pages.length > 0 && <div className="flex gap-2 overflow-x-auto border-t border-indigo-100 px-3 py-2.5">{pages.slice(0, 8).map((page, index) => { const item = asRecord(page); const visuals = Array.isArray(item?.visuals) ? item.visuals.length : 0; return <div key={index} className="w-28 shrink-0 rounded-lg border border-indigo-100 bg-white p-2"><div className="mb-2 grid aspect-[16/9] place-items-center rounded bg-indigo-50 text-indigo-300"><BarChart2 className="size-4" /></div><p className="truncate text-[10px] font-bold text-zinc-700">{formatValue(item?.display_name ?? item?.name ?? `Page ${index + 1}`)}</p><p className="text-[9px] text-zinc-400">{visuals} visual{visuals === 1 ? "" : "s"}</p></div>; })}</div>}
      {Boolean(root.candidate_manifest_path) && (
        <div className="border-t border-indigo-100 bg-white/60 px-3 py-2">
          <p className="flex items-center gap-1.5 truncate font-mono text-[9px] text-zinc-400"><FileText className="size-3 shrink-0" />{String(root.candidate_manifest_path)}</p>
        </div>
      )}
    </div>
  );
}

function ConnectionPanel({ data }: { data: unknown }) {
  const items = Array.isArray(data) ? data : [data];
  const records = items.map(asRecord).filter((item): item is JsonRecord => item !== null);
  if (!records.length) return <ValuePanel data={data} />;
  return <div className="space-y-2">{records.map((item, index) => <div key={index} className="flex items-center gap-3 rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 to-white p-3"><span className="relative grid size-9 shrink-0 place-items-center rounded-lg bg-blue-600 text-white"><Database className="size-4" /><span className="absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full border-2 border-white bg-emerald-500" /></span><div className="min-w-0 flex-1"><p className="truncate text-xs font-bold text-zinc-900">{formatValue(item.connectionName ?? item.name ?? item.serverName ?? "Power BI Desktop")}</p><p className="truncate font-mono text-[10px] text-blue-700">{item.port ? `localhost:${String(item.port)}` : formatValue(item.server ?? item.database ?? "Connected")}</p></div><span className="rounded-full bg-emerald-100 px-2 py-1 text-[9px] font-bold uppercase text-emerald-700">Available</span></div>)}</div>;
}

function VersionTimeline({ versions }: { versions: unknown[] }) {
  return <div className="space-y-0.5">{versions.map((entry, index) => { const item = asRecord(entry) ?? {}; return <div key={index} className="flex gap-3"><div className="flex w-5 flex-col items-center"><span className={`mt-2 size-2 rounded-full ${item.active ? "bg-indigo-600 ring-4 ring-indigo-100" : "bg-zinc-300"}`} />{index < versions.length - 1 && <span className="h-full w-px bg-zinc-200" />}</div><div className="mb-2 min-w-0 flex-1 rounded-lg border border-zinc-200 bg-white px-3 py-2"><div className="flex items-center justify-between"><p className="text-[11px] font-bold text-zinc-800">Version {String(item.version ?? index + 1)}</p>{item.active ? <span className="text-[9px] font-bold uppercase text-indigo-600">Active</span> : null}</div><p className="truncate text-[10px] text-zinc-500">{String(item.reason ?? item.created_at ?? "Saved revision")}</p></div></div>; })}</div>;
}

function RelationshipPanel({ data }: { data: unknown }) {
  const items = (Array.isArray(data) ? data : [data]).map(asRecord).filter((item): item is JsonRecord => item !== null);
  return <div className="space-y-2">{items.map((item, index) => <div key={index} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-xl border border-violet-200 bg-white p-3"><div className="min-w-0 text-right"><p className="truncate text-xs font-bold text-zinc-800">{formatValue(item.fromTable ?? "Source")}</p><p className="truncate font-mono text-[10px] text-violet-600">{formatValue(item.fromColumn)}</p></div><div className="flex items-center gap-1 text-violet-400"><span className="rounded bg-violet-100 px-1 text-[9px]">{formatValue(item.fromCardinality ?? "1")}</span><ArrowRightLeft className="size-4" /><span className="rounded bg-violet-100 px-1 text-[9px]">{formatValue(item.toCardinality ?? "*")}</span></div><div className="min-w-0"><p className="truncate text-xs font-bold text-zinc-800">{formatValue(item.toTable ?? "Target")}</p><p className="truncate font-mono text-[10px] text-violet-600">{formatValue(item.toColumn)}</p></div></div>)}</div>;
}

function EntityList({ data }: { data: unknown[] }) {
  const typeColor = (type: string) => {
    const value = type.toLowerCase();
    if (/(int|float|decimal|number|numeric|double)/.test(value)) return "bg-emerald-100 text-emerald-700";
    if (/(string|varchar|char|text|name)/.test(value)) return "bg-sky-100 text-sky-700";
    if (/(bool)/.test(value)) return "bg-amber-100 text-amber-700";
    if (/(date|time|timestamp|datetime)/.test(value)) return "bg-purple-100 text-purple-700";
    return "bg-violet-100 text-violet-700";
  };
  return <div className="max-h-60 overflow-auto rounded-xl border border-violet-200 bg-white divide-y divide-zinc-100">{data.map((entry, index) => { const item = asRecord(entry); const type = String(item?.dataType ?? item?.type ?? ""); const rows = typeof item?.row_count === "number" ? item.row_count : undefined; return <div key={index} className="flex items-center justify-between gap-3 px-3 py-2 hover:bg-violet-50/50"><div className="min-w-0"><p className="truncate font-mono text-[11px] font-semibold text-zinc-800">{formatValue(item?.name ?? item?.tableName ?? item?.table ?? entry)}</p>{item?.description ? <p className="truncate text-[9px] text-zinc-400">{String(item.description)}</p> : null}</div><div className="flex shrink-0 items-center gap-1.5">{rows !== undefined ? <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[9px] text-zinc-500">{rows.toLocaleString()}</span> : null}{type ? <span className={`rounded px-1.5 py-0.5 font-mono text-[9px] ${typeColor(type)}`}>{type}</span> : null}</div></div>; })}</div>;
}

function ArtifactPanel({ data }: { data: unknown }) {
  const record = asRecord(data);
  if (!record) return <ValuePanel data={data} />;
  const paths = Object.entries(record).filter(([key, value]) => (key.includes("path") || key.includes("artifact") || key.includes("url")) && (typeof value === "string" || Array.isArray(value)));
  return <div className="space-y-2">{paths.flatMap(([key, value]) => (Array.isArray(value) ? value : [value]).map((path, index) => <div key={`${key}-${index}`} className="flex items-center gap-3 rounded-xl border border-pink-200 bg-white px-3 py-2.5"><span className="grid size-8 shrink-0 place-items-center rounded-lg bg-pink-50 text-pink-600">{String(path).match(/\.(png|jpg|jpeg)$/i) ? <ImageIcon className="size-4" /> : <FileText className="size-4" />}</span><div className="min-w-0 flex-1"><p className="text-[9px] font-bold uppercase tracking-wider text-zinc-400">{titleCase(key)}</p><p className="truncate font-mono text-[10px] text-zinc-700">{String(path)}</p></div><ExternalLink className="size-3.5 text-zinc-300" /></div>))}</div>;
}

const SEVERITY_STYLES: Record<string, { label: string; cls: string }> = {
  error: { label: "Error", cls: "bg-red-100 text-red-700 ring-red-200" },
  warning: { label: "Warning", cls: "bg-amber-100 text-amber-700 ring-amber-200" },
  suggestion: { label: "Suggestion", cls: "bg-sky-100 text-sky-700 ring-sky-200" },
};

function ReviewPanel({ data, images, apiBase }: { data: unknown; images?: string[]; apiBase?: string }) {
  const record = asRecord(data);
  if (!record) return <ValuePanel data={data} />;
  const findings = [record.findings, record.issues, record.recommendations].flatMap((value) => Array.isArray(value) ? value : []).filter(Boolean);
  const decision = record.decision ?? record.action ?? record.outcome;
  const approved = record.approved === true || record.status === "approved" || record.accepted === true;
  const score = typeof record.score === "number" ? record.score : undefined;
  const summary = record.summary ? String(record.summary) : "";
  const verdictCls = approved ? "from-emerald-500 to-teal-600" : "from-purple-600 to-fuchsia-600";
  const verdictIcon = approved ? <Check className="size-4" /> : <Sparkles className="size-4" />;
  return (
    <div className="space-y-2.5">
      <div className={`rounded-xl bg-gradient-to-r p-3 text-white ${verdictCls}`}>
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-full bg-white/20">{verdictIcon}</span>
          <p className="text-xs font-bold uppercase tracking-wide">{approved ? "Approved" : (decision ? titleCase(String(decision)) : "Visual QA review")}</p>
          {score !== undefined && <span className="ml-auto rounded-full bg-white/20 px-2 py-0.5 font-mono text-[10px] font-bold">{score}</span>}
        </div>
        {summary ? <p className="mt-1.5 text-[10px] leading-relaxed text-white/90">{summary}</p> : null}
      </div>
      {images && images.length > 0 && (
        <ImageGallery images={images} apiBase={apiBase} />
      )}
      {findings.length > 0 && (
        <div className="space-y-1.5">
          {findings.map((finding, index) => {
            const item = asRecord(finding);
            const severity = String(item?.severity ?? "warning").toLowerCase();
            const badge = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.warning;
            const message = item?.message ?? item?.recommendation ?? item?.problem ?? finding;
            return (
              <div key={index} className="flex gap-2 rounded-lg border border-purple-100 bg-white p-2.5">
                <span className={`mt-0.5 h-fit shrink-0 rounded-full px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider ring-1 ${badge.cls}`}>{badge.label}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] leading-relaxed text-zinc-700">{formatValue(message)}</p>
                  {Boolean(item?.recommendation) && String(item?.recommendation) !== String(message) && (
                    <p className="mt-0.5 text-[10px] text-purple-600"><span className="font-semibold">Fix: </span>{formatValue(item?.recommendation)}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ImageGallery({ images, apiBase }: { images: string[]; apiBase?: string }) {
  const resolve = (src: string) => (src.startsWith("http") ? src : `${apiBase ?? ""}${src}`);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  if (!images.length) return null;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-pink-50 text-pink-600"><ImageIcon className="size-3.5" /></span>
        <p className="text-[10px] font-bold uppercase tracking-wider text-pink-700">Rendered preview{images.length > 1 ? "s" : ""}</p>
        <span className="ml-auto font-mono text-[9px] text-zinc-400">{images.length}</span>
      </div>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="group relative block w-full overflow-hidden rounded-xl border border-pink-200 bg-pink-50/40"
        aria-label="Open rendered dashboard preview"
      >
        <img
          src={resolve(images[active])}
          alt="Rendered Power BI dashboard"
          className="max-h-96 w-full object-contain transition-transform duration-300 group-hover:scale-[1.01]"
        />
        {images.length > 1 && (
          <span className="absolute bottom-2 right-2 rounded-full bg-black/60 px-2 py-0.5 font-mono text-[10px] text-white">
            {active + 1} / {images.length}
          </span>
        )}
      </button>
      {images.length > 1 && (
        <div className="flex gap-1.5 overflow-x-auto pb-0.5">
          {images.map((src, index) => (
            <button
              key={src}
              type="button"
              onClick={() => setActive(index)}
              className={`h-12 w-16 shrink-0 overflow-hidden rounded-md border-2 transition-colors ${index === active ? "border-pink-500" : "border-transparent opacity-60 hover:opacity-100"}`}
              aria-label={`Preview ${index + 1}`}
            >
              <img src={resolve(src)} alt={`Preview ${index + 1}`} className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6" role="dialog" aria-modal="true" onClick={() => setOpen(false)}>
          <div className="relative max-h-full max-w-6xl overflow-auto rounded-2xl bg-white p-3 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => setOpen(false)} className="absolute right-2 top-2 grid size-8 place-items-center rounded-full bg-black/60 text-white hover:bg-black/80" aria-label="Close preview"><X className="size-4" /></button>
            <img src={resolve(images[active])} alt="Rendered Power BI dashboard (large view)" className="max-h-[80vh] w-auto object-contain" />
          </div>
        </div>
      )}
    </div>
  );
}

function ValuePanel({ data }: { data: unknown }) {
  if (typeof data === "string") return <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-50 p-3 font-mono text-[11px] leading-relaxed text-zinc-700">{data}</pre>;
  if (Array.isArray(data)) return data.length ? <EntityList data={data} /> : <EmptyState label="No items returned" />;
  const record = asRecord(data);
  if (!record) return null;
  const entries = Object.entries(record).filter(([, value]) => value !== null && typeof value !== "object").slice(0, 12);
  return <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">{entries.map(([key, value]) => <div key={key} className="rounded-lg border border-zinc-200 bg-white px-3 py-2"><p className="text-[9px] font-bold uppercase tracking-wider text-zinc-400">{titleCase(key)}</p><p className="mt-0.5 truncate font-mono text-[11px] text-zinc-700">{formatValue(value)}</p></div>)}</div>;
}

function ToolBody({ toolCall, data, theme, apiBase }: { toolCall: ToolCall; data: unknown; theme: ToolTheme; apiBase?: string }) {
  const operation = getOperation(toolCall.arguments);
  if (theme.kind === "query") {
    const record = asRecord(data);
    const rows = Array.isArray(data) ? data : Array.isArray(record?.rows) ? record.rows : Array.isArray(record?.data) ? record.data : Array.isArray(record?.results) ? record.results : null;
    if (rows) return <DataGrid rows={rows} />;
  }
  if (toolCall.name === "run_python_sandbox") return <CodePanel code={String(toolCall.arguments.code ?? "")} language="Python" output={typeof data === "string" ? data : JSON.stringify(data, null, 2)} />;
  if (toolCall.name === "format_dax") return <CodePanel code={typeof data === "string" ? data : String(toolCall.arguments.dax_code ?? "")} language="DAX" />;
  if (toolCall.name === "bigquery_list_tables") {
    const record = asRecord(data);
    return <EntityList data={Array.isArray(record?.tables) ? record.tables : []} />;
  }
  if (toolCall.name === "bigquery_get_table_schema") {
    const record = asRecord(data);
    return <EntityList data={Array.isArray(record?.fields) ? record.fields : []} />;
  }
  if (toolCall.name === "bigquery_semantic_catalog") {
    const record = asRecord(data);
    const tables = Array.isArray(record?.tables) ? record.tables : [];
    const fields = tables.reduce((count, table) => {
      const item = asRecord(table);
      return count + (Array.isArray(item?.columns) ? item.columns.length : 0) + (Array.isArray(item?.measures) ? item.measures.length : 0);
    }, 0);
    return (
      <div className="space-y-2">
        <div className="grid grid-cols-2 gap-2"><Stat label="Tables" value={tables.length} /><Stat label="Report fields" value={fields} /></div>
        <div className="flex flex-wrap gap-1.5">{tables.slice(0, 24).map((table, index) => {
          const item = asRecord(table);
          const name = String(item?.name ?? item?.table_name ?? `Table ${index + 1}`);
          const cols = Array.isArray(item?.columns) ? item.columns.length : 0;
          const measures = Array.isArray(item?.measures) ? item.measures.length : 0;
          const rowCount = typeof item?.row_count === "number" ? item.row_count : undefined;
          return (
            <span key={`${name}-${index}`} className="inline-flex items-center gap-1.5 rounded-lg border border-violet-200 bg-white px-2 py-1" title={name}>
              <Table2 className="size-3 text-violet-500" />
              <span className="max-w-40 truncate text-[10px] font-semibold text-zinc-700">{name}</span>
              <span className="text-[9px] text-zinc-400">{cols}c{measures ? ` · ${measures}m` : ""}</span>
              {rowCount !== undefined && <span className="rounded bg-violet-50 px-1 font-mono text-[9px] text-violet-600">{rowCount.toLocaleString()}</span>}
            </span>
          );
        })}</div>
      </div>
    );
  }
  if (theme.kind === "validation") return <ValidationPanel data={data} />;
  if (theme.kind === "connection") return <ConnectionPanel data={data} />;
  if (toolCall.name === "list_dashboard_versions" && Array.isArray(data)) return <VersionTimeline versions={data} />;
  if (theme.kind === "workspace") return <DashboardPanel data={data} images={toolCall.images} apiBase={apiBase} />;
  if (toolCall.name === "relationship_operations") return <RelationshipPanel data={data} />;
  if (theme.kind === "model" && Array.isArray(data)) return <EntityList data={data} />;
  if (toolCall.name === "measure_operations" && ["CreateMeasure", "UpdateMeasure", "GetMeasure"].includes(operation ?? "")) {
    const request = asRecord(toolCall.arguments.request) ?? toolCall.arguments;
    return <div className="space-y-2"><div className="flex items-center gap-2 rounded-lg bg-violet-50 px-3 py-2 text-xs"><span className="font-mono font-bold text-violet-800">{request.tableName ? `${String(request.tableName)} · ` : ""}[{String(request.name ?? request.measureName ?? "Measure")}]</span>{request.formatString ? <span className="ml-auto rounded bg-white px-2 py-0.5 font-mono text-[9px] text-violet-600">{String(request.formatString)}</span> : null}</div>{request.expression ? <CodePanel code={String(request.expression)} language="DAX measure" /> : <ValuePanel data={data} />}</div>;
  }
  if (theme.kind === "render") return <ArtifactPanel data={data} />;
  if (theme.kind === "review") return <ReviewPanel data={data} images={toolCall.images} apiBase={apiBase} />;
  if (theme.kind === "publish") {
    const record = asRecord(data);
    const entries = ([
      ["report_id", record?.report_id],
      ["workspace_id", record?.workspace_id],
      ["semantic_model_id", record?.semantic_model_id],
      ["dataset_id", record?.dataset_id],
    ] as [string, unknown][]).filter(([, value]) => typeof value === "string" && value) as [string, string][];
    const url = record?.url ? String(record.url) : null;
    return (
      <div className="overflow-hidden rounded-xl border border-sky-200">
        <div className="flex items-center gap-3 bg-gradient-to-r from-sky-600 to-cyan-600 p-3.5 text-white">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-white/20"><Rocket className="size-4" /></span>
          <div className="min-w-0"><p className="text-xs font-bold">Published to Microsoft Fabric</p><p className="truncate text-[10px] text-sky-100">{formatValue(record?.display_name ?? "Report is available in the staging workspace")}</p></div>
          {url ? <a href={url} target="_blank" rel="noreferrer" className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-lg bg-white/20 px-2 py-1 text-[10px] font-semibold hover:bg-white/30" aria-label="Open report in Fabric"><ExternalLink className="size-3" /> Open</a> : null}
        </div>
        {entries.length > 0 && <div className="grid grid-cols-1 gap-1.5 bg-white p-3 sm:grid-cols-2">{entries.map(([label, value]) => <div key={label} className="rounded-lg bg-sky-50 px-2.5 py-1.5 ring-1 ring-sky-100"><p className="text-[8px] font-bold uppercase tracking-wider text-sky-500">{titleCase(label)}</p><p className="truncate font-mono text-[10px] text-sky-900">{value}</p></div>)}</div>}
      </div>
    );
  }
  if (theme.kind === "desktop") {
    const record = asRecord(data);
    return <div className="flex items-center gap-3 rounded-xl border border-cyan-200 bg-cyan-50 p-3"><span className="grid size-9 place-items-center rounded-lg bg-cyan-600 text-white"><Monitor className="size-4" /></span><div className="min-w-0"><p className="text-xs font-bold text-zinc-900">{record?.opened ? "Opened in Power BI Desktop" : "Desktop package prepared"}</p><p className="truncate font-mono text-[10px] text-cyan-800">{formatValue(record?.pbir_path ?? record?.report_path ?? record?.semantic_model_path)}</p></div></div>;
  }
  return <ValuePanel data={data} />;
}

export function ToolCallCard({ toolCall, apiBase }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const data = useMemo(() => parseResult(toolCall.result), [toolCall.result]);
  const theme = getTheme(toolCall.name);
  const action = getActionSummary(toolCall, data);
  const isRunning = toolCall.status === "running" || (toolCall.status === undefined && toolCall.result === undefined && !toolCall.error);
  const startedAtRef = useRef<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  useEffect(() => {
    if (isRunning && startedAtRef.current === null) startedAtRef.current = Date.now();
    if (!isRunning) return;
    const tick = () => setElapsedMs(Date.now() - (startedAtRef.current ?? Date.now()));
    tick();
    const id = window.setInterval(tick, 500);
    return () => window.clearInterval(id);
  }, [isRunning]);
  const durationMs = startedAtRef.current === null ? undefined : isRunning ? elapsedMs : Date.now() - startedAtRef.current;

  return (
    <article aria-live={isRunning ? "polite" : undefined} className={`relative overflow-hidden rounded-2xl border bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04),0_8px_24px_rgba(0,0,0,0.035)] ${toolCall.error ? "border-red-200" : theme.borderClass}`}>
      <div className="absolute inset-y-0 left-0 w-1" style={{ backgroundColor: toolCall.error ? "#dc2626" : theme.accent }} />
      <header className="flex items-center gap-3 px-4 py-3">
        <span className={`grid size-9 shrink-0 place-items-center rounded-xl border ${theme.softClass} ${theme.iconClass} ${theme.borderClass}`}>{theme.icon}</span>
        <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-1.5"><p className="truncate text-xs font-bold text-zinc-900">{theme.label}</p><Status toolCall={toolCall} durationMs={durationMs} /></div><p className="mt-0.5 truncate text-[10px] text-zinc-500">{action}</p></div>
        <button onClick={() => setExpanded((value) => !value)} className="grid size-7 shrink-0 place-items-center rounded-lg text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700" aria-expanded={expanded} aria-label="Show technical details"><ChevronDown className={`size-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} /></button>
      </header>

      {isRunning && <div className="px-4 pb-3"><div className={`relative h-1 overflow-hidden rounded-full ${theme.softClass}`}><span className="absolute inset-y-0 w-1/3 animate-[tool-progress_1.4s_ease-in-out_infinite] rounded-full" style={{ backgroundColor: theme.accent }} /></div></div>}
      {toolCall.error && <div className="px-4 pb-3"><div className="flex gap-2.5 rounded-xl border border-red-200 bg-red-50 p-3"><AlertCircle className="mt-0.5 size-4 shrink-0 text-red-600" /><div className="min-w-0"><p className="text-[10px] font-bold uppercase tracking-wider text-red-700">Tool failed</p><p className="mt-1 text-[11px] leading-relaxed text-red-800">The agent can use this error to correct the request and retry. Technical detail:</p><pre className="mt-1 max-h-28 overflow-auto whitespace-pre-wrap font-mono text-[10px] leading-relaxed text-red-800">{toolCall.error}</pre></div></div></div>}
      {(toolCall.status === "complete" || toolCall.result !== undefined) && !toolCall.error && (
        <div className="px-4 pb-4 space-y-3">
          <ToolBody toolCall={toolCall} data={data} theme={theme} apiBase={apiBase} />
          {toolCall.images && toolCall.images.length > 0 && theme.kind !== "review" && theme.kind !== "workspace" && <ImageGallery images={toolCall.images} apiBase={apiBase} />}
        </div>
      )}

      {expanded && <div className="border-t border-zinc-100 bg-zinc-50/80 px-4 py-3"><div className="mb-2 flex items-center justify-between"><p className="text-[9px] font-bold uppercase tracking-[0.16em] text-zinc-400">Technical details</p><span className="font-mono text-[9px] text-zinc-400">{toolCall.name}</span></div><pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded-lg border border-zinc-200 bg-white p-3 font-mono text-[10px] leading-relaxed text-zinc-600">{JSON.stringify(toolCall.arguments, null, 2)}</pre></div>}
    </article>
  );
}
