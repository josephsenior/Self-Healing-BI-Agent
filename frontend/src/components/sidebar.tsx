"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  MessageSquarePlus,
  Trash2,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  MessageSquare,
  BarChart3,
  Database,
  ShieldCheck,
  Settings,
  Save,
  X,
  Loader2,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  WifiOff,
  Search,
  Wrench,
  Sparkles,
  SlidersHorizontal,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import type { ConnectionStatus, AgentConfig } from "@/types";

export interface ConversationSummary {
  id: string;
  title: string;
  updatedAt: string;
}

interface SidebarProps {
  connectionStatus: ConnectionStatus;
  agentConfig: AgentConfig | null;
  discoveredTools: string[];
  onReconnect: () => void;
  onConfigUpdate: (newConfig: AgentConfig) => Promise<boolean>;
  reasoningEffort: string;
  onReasoningEffortChange: (val: string) => void;
  conversations: ConversationSummary[];
  activeConversationId: string;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (id: string) => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const PROVIDER_MODELS = {
  gemini: "gemini-3.5-flash",
  openai: "gpt-4o",
  anthropic: "claude-3-5-sonnet-latest",
} as const;

const PROVIDER_LABELS: Record<string, string> = {
  gemini: "Google Gemini",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

function formatTimestamp(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return "";
    const now = new Date();
    const isToday =
      date.getDate() === now.getDate() &&
      date.getMonth() === now.getMonth() &&
      date.getFullYear() === now.getFullYear();

    if (isToday) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

function groupConversations(conversations: ConversationSummary[]) {
  const groups: { label: string; items: ConversationSummary[] }[] = [];
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;
  const startOfLast7Days = startOfToday - 7 * 86400000;

  const today: ConversationSummary[] = [];
  const yesterday: ConversationSummary[] = [];
  const previous7Days: ConversationSummary[] = [];
  const older: ConversationSummary[] = [];

  for (const c of conversations) {
    const time = new Date(c.updatedAt).getTime();
    if (isNaN(time) || time >= startOfToday) {
      today.push(c);
    } else if (time >= startOfYesterday) {
      yesterday.push(c);
    } else if (time >= startOfLast7Days) {
      previous7Days.push(c);
    } else {
      older.push(c);
    }
  }

  if (today.length) groups.push({ label: "Today", items: today });
  if (yesterday.length) groups.push({ label: "Yesterday", items: yesterday });
  if (previous7Days.length) groups.push({ label: "Previous 7 Days", items: previous7Days });
  if (older.length) groups.push({ label: "Older", items: older });

  return groups;
}

export function Sidebar({
  connectionStatus,
  agentConfig,
  discoveredTools,
  onReconnect,
  onConfigUpdate,
  reasoningEffort,
  onReasoningEffortChange,
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  mobileOpen,
  onCloseMobile,
  collapsed,
  onToggleCollapse,
}: SidebarProps) {
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [transport, setTransport] = useState("");
  const [sseUrl, setSseUrl] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [searchFilter, setSearchFilter] = useState("");
  const [toolsExpanded, setToolsExpanded] = useState(false);

  // Sync config when modal opens or agentConfig changes
  useEffect(() => {
    if (agentConfig) {
      setProvider(agentConfig.llm_provider || "gemini");
      setModel(agentConfig.llm_model || "gemini-3.5-flash");
      setTransport(agentConfig.transport_mode || "STDIO");
      setSseUrl(agentConfig.sse_url || "");
    }
  }, [agentConfig, isConfigModalOpen]);

  // Handle ESC key for modal
  useEffect(() => {
    if (!isConfigModalOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isSaving) {
        setIsConfigModalOpen(false);
        setErrorMsg("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isConfigModalOpen, isSaving]);

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!provider || !model || !transport) {
      setErrorMsg("Please fill in all required fields.");
      return;
    }
    if (transport.toUpperCase() === "SSE" && !sseUrl.trim()) {
      setErrorMsg("SSE URL is required when using SSE transport.");
      return;
    }

    setIsSaving(true);
    setErrorMsg("");
    try {
      const success = await onConfigUpdate({
        llm_provider: provider.toLowerCase(),
        llm_model: model.trim(),
        transport_mode: transport.toUpperCase(),
        sse_url: transport.toUpperCase() === "SSE" ? sseUrl.trim() : null,
      });
      if (success) {
        setIsConfigModalOpen(false);
      } else {
        setErrorMsg("Failed to update configuration.");
      }
    } catch {
      setErrorMsg("An error occurred while saving.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleProviderChange = (newProvider: string) => {
    setProvider(newProvider);
    setModel(PROVIDER_MODELS[newProvider as keyof typeof PROVIDER_MODELS] || "");
  };

  const filteredConversations = useMemo(() => {
    if (!searchFilter.trim()) return conversations;
    const q = searchFilter.toLowerCase();
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [conversations, searchFilter]);

  const groupedConversations = useMemo(() => {
    return groupConversations(filteredConversations);
  }, [filteredConversations]);

  const statusDetails = useMemo(() => {
    switch (connectionStatus) {
      case "connected":
        return {
          dotClass: "bg-emerald-500",
          text: "Connected",
          textClass: "text-emerald-700 font-medium",
          badgeBg: "bg-emerald-50 text-emerald-700 border-emerald-200",
          icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />,
        };
      case "connecting":
        return {
          dotClass: "bg-amber-500 animate-pulse",
          text: "Connecting…",
          textClass: "text-amber-700 font-medium",
          badgeBg: "bg-amber-50 text-amber-700 border-amber-200",
          icon: <RefreshCw className="w-3.5 h-3.5 text-amber-600 animate-spin" />,
        };
      case "error":
        return {
          dotClass: "bg-rose-500",
          text: "Error",
          textClass: "text-rose-700 font-medium",
          badgeBg: "bg-rose-50 text-rose-700 border-rose-200",
          icon: <AlertCircle className="w-3.5 h-3.5 text-rose-600" />,
        };
      default:
        return {
          dotClass: "bg-zinc-400",
          text: "Offline",
          textClass: "text-zinc-500 font-medium",
          badgeBg: "bg-zinc-100 text-zinc-600 border-zinc-200",
          icon: <WifiOff className="w-3.5 h-3.5 text-zinc-400" />,
        };
    }
  }, [connectionStatus]);

  const currentProviderLabel = agentConfig
    ? PROVIDER_LABELS[agentConfig.llm_provider] || agentConfig.llm_provider
    : "Gemini";

  return (
    <>
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          role="button"
          tabIndex={0}
          aria-label="Close sidebar overlay"
          onClick={onCloseMobile}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onCloseMobile();
          }}
          className="fixed inset-0 z-40 bg-zinc-900/40 backdrop-blur-xs transition-opacity lg:hidden"
        />
      )}

      {/* Main Sidebar */}
      <aside
        className={`workspace-sidebar fixed inset-y-0 left-0 z-40 flex flex-col bg-white border-r border-zinc-200/90 shadow-xl transition-all duration-200 ease-in-out lg:static lg:z-auto lg:h-screen lg:shadow-none ${
          mobileOpen
            ? "translate-x-0 w-[272px]"
            : collapsed
            ? "w-[64px] -translate-x-full lg:w-[64px] lg:translate-x-0"
            : "w-[272px] -translate-x-full lg:w-[272px] lg:translate-x-0"
        }`}
        aria-label="Navigation sidebar"
      >
        {/* Top Header */}
        <div className="flex items-center justify-between h-14 px-3.5 border-b border-zinc-100 bg-white/95 backdrop-blur-xs shrink-0">
          {!collapsed ? (
            <>
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 via-indigo-600 to-sky-500 flex items-center justify-center text-white shadow-xs shrink-0">
                  <Sparkles className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-sm tracking-tight text-zinc-900 leading-none">Prism</span>
                    <span className="px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-blue-700 bg-blue-50 rounded border border-blue-100/60 leading-none">
                      AI
                    </span>
                  </div>
                  <p className="text-[11px] text-zinc-400 font-normal truncate mt-0.5 leading-none">Data Intelligence</p>
                </div>
              </div>

              <div className="flex items-center gap-1">
                {/* Desktop Collapse Button */}
                <button
                  type="button"
                  onClick={onToggleCollapse}
                  className="hidden lg:flex items-center justify-center w-7 h-7 rounded-md text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors"
                  title="Collapse sidebar"
                  aria-label="Collapse sidebar"
                >
                  <PanelLeftClose className="w-4 h-4" />
                </button>
                {/* Mobile Close Button */}
                <button
                  type="button"
                  onClick={onCloseMobile}
                  className="lg:hidden flex items-center justify-center w-7 h-7 rounded-md text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors"
                  aria-label="Close sidebar"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </>
          ) : (
            <div className="w-full flex items-center justify-center">
              <button
                type="button"
                onClick={onToggleCollapse}
                className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 via-indigo-600 to-sky-500 flex items-center justify-center text-white shadow-xs hover:opacity-90 transition-opacity"
                title="Expand sidebar"
                aria-label="Expand sidebar"
              >
                <Sparkles className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>

        {/* Action Button Section */}
        <div className="p-3 pb-2 shrink-0">
          {!collapsed ? (
            <button
              type="button"
              onClick={() => {
                onNewConversation();
                if (mobileOpen) onCloseMobile();
              }}
              className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs shadow-xs transition-all duration-150 active:scale-[0.99] group"
            >
              <span className="flex items-center gap-2">
                <MessageSquarePlus className="w-4 h-4 text-blue-100 group-hover:text-white transition-colors" />
                <span>New Analysis</span>
              </span>
              <span className="text-[10px] font-mono text-blue-200/80 bg-blue-700/60 px-1.5 py-0.5 rounded">
                +
              </span>
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                onNewConversation();
                if (mobileOpen) onCloseMobile();
              }}
              className="w-10 h-10 mx-auto flex items-center justify-center rounded-lg bg-blue-600 hover:bg-blue-700 text-white shadow-xs transition-all active:scale-95"
              title="New Analysis"
              aria-label="New Analysis"
            >
              <MessageSquarePlus className="w-4 h-4" />
            </button>
          )}

          {/* Quick Search Filter (Only when expanded and has conversations) */}
          {!collapsed && conversations.length > 2 && (
            <div className="relative mt-2">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-400 pointer-events-none" />
              <input
                type="text"
                placeholder="Filter chats…"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="w-full pl-8 pr-6 py-1.5 text-xs bg-zinc-50 hover:bg-zinc-100/80 focus:bg-white text-zinc-800 placeholder-zinc-400 rounded-md border border-zinc-200/80 focus:border-blue-500 focus:outline-none transition-colors"
              />
              {searchFilter && (
                <button
                  type="button"
                  onClick={() => setSearchFilter("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600"
                  aria-label="Clear filter"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          )}
        </div>

        {/* Scrollable Conversation List */}
        <div className="flex-1 overflow-y-auto px-2.5 py-1 min-h-0 space-y-3 select-none">
          {!collapsed ? (
            groupedConversations.length > 0 ? (
              groupedConversations.map((group) => (
                <div key={group.label} className="space-y-0.5">
                  <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                    {group.label}
                  </div>
                  <div className="space-y-0.5" role="list">
                    {group.items.map((conv) => {
                      const isActive = activeConversationId === conv.id;
                      return (
                        <div
                          key={conv.id}
                          className={`group relative flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer transition-all duration-150 ${
                            isActive
                              ? "bg-blue-50/90 text-blue-900 font-medium"
                              : "text-zinc-600 hover:bg-zinc-100/80 hover:text-zinc-900"
                          }`}
                          onClick={() => {
                            onSelectConversation(conv.id);
                            if (mobileOpen) onCloseMobile();
                          }}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              onSelectConversation(conv.id);
                              if (mobileOpen) onCloseMobile();
                            }
                          }}
                        >
                          <MessageSquare
                            className={`w-3.5 h-3.5 shrink-0 transition-colors ${
                              isActive ? "text-blue-600" : "text-zinc-400 group-hover:text-zinc-600"
                            }`}
                          />
                          <div className="min-w-0 flex-1">
                            <p className="text-xs truncate leading-snug">
                              {conv.title || "Untitled conversation"}
                            </p>
                          </div>

                          <span className="text-[10px] text-zinc-400 shrink-0 font-normal group-hover:hidden">
                            {formatTimestamp(conv.updatedAt)}
                          </span>

                          {/* Delete Action Button */}
                          {conversations.length > 1 && (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onDeleteConversation(conv.id);
                              }}
                              className="hidden group-hover:flex items-center justify-center w-5 h-5 rounded text-zinc-400 hover:text-rose-600 hover:bg-rose-50 transition-colors shrink-0"
                              title="Delete conversation"
                              aria-label={`Delete ${conv.title}`}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))
            ) : (
              <div className="py-8 text-center px-4">
                <p className="text-xs text-zinc-400">
                  {searchFilter ? "No matching conversations" : "No conversations yet"}
                </p>
              </div>
            )
          ) : (
            /* Collapsed Conversation Icons */
            <div className="space-y-1.5 py-1">
              {conversations.slice(0, 10).map((conv) => {
                const isActive = activeConversationId === conv.id;
                return (
                  <button
                    key={conv.id}
                    type="button"
                    onClick={() => {
                      onSelectConversation(conv.id);
                      if (mobileOpen) onCloseMobile();
                    }}
                    className={`w-9 h-9 mx-auto flex items-center justify-center rounded-lg transition-colors ${
                      isActive
                        ? "bg-blue-50 text-blue-600 ring-1 ring-blue-200"
                        : "text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100"
                    }`}
                    title={conv.title}
                    aria-label={conv.title}
                  >
                    <MessageSquare className="w-4 h-4" />
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Collapsible Discovered Tools Section (Only when expanded) */}
        {!collapsed && discoveredTools.length > 0 && (
          <div className="px-3 py-1.5 border-t border-zinc-100 shrink-0">
            <button
              type="button"
              onClick={() => setToolsExpanded(!toolsExpanded)}
              className="w-full flex items-center justify-between py-1.5 px-2 rounded-md text-[11px] font-medium text-zinc-500 hover:text-zinc-800 hover:bg-zinc-50 transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <Wrench className="w-3 h-3 text-zinc-400" />
                <span>Capabilities</span>
                <span className="text-[10px] font-mono px-1 py-0.5 rounded bg-zinc-100 text-zinc-600">
                  {discoveredTools.length}
                </span>
              </span>
              <ChevronDown
                className={`w-3.5 h-3.5 text-zinc-400 transition-transform duration-200 ${
                  toolsExpanded ? "rotate-180" : ""
                }`}
              />
            </button>

            {toolsExpanded && (
              <div className="mt-1.5 p-2 bg-zinc-50/80 rounded-lg border border-zinc-200/60 max-h-36 overflow-y-auto">
                <div className="flex flex-wrap gap-1">
                  {discoveredTools.map((tool) => (
                    <span
                      key={tool}
                      className="px-1.5 py-0.5 text-[10px] font-mono bg-white border border-zinc-200 rounded text-zinc-600 truncate max-w-full"
                      title={tool}
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Bottom Footer / Status & Settings */}
        <div className="p-3 border-t border-zinc-100 bg-zinc-50/60 shrink-0">
          {!collapsed ? (
            <div className="flex items-center justify-between gap-2">
              {/* Status & Model info */}
              <div className="min-w-0 flex-1 flex items-center gap-2">
                <div className="relative flex items-center justify-center">
                  <span className={`w-2 h-2 rounded-full ${statusDetails.dotClass}`} />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-medium text-zinc-800 truncate leading-tight">
                    {agentConfig?.llm_model || "gemini-3.5-flash"}
                  </p>
                  <p className="text-[10px] text-zinc-400 truncate leading-tight">
                    {currentProviderLabel} · {statusDetails.text}
                  </p>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-1 shrink-0">
                {(connectionStatus === "disconnected" || connectionStatus === "error") && (
                  <button
                    type="button"
                    onClick={onReconnect}
                    className="p-1.5 rounded-md text-zinc-500 hover:text-blue-600 hover:bg-white border border-transparent hover:border-zinc-200 transition-colors shadow-2xs"
                    title="Reconnect"
                    aria-label="Reconnect"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setIsConfigModalOpen(true)}
                  className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-800 hover:bg-white border border-transparent hover:border-zinc-200 transition-colors shadow-2xs"
                  title="Agent Settings"
                  aria-label="Agent Settings"
                >
                  <Settings className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ) : (
            /* Collapsed footer */
            <div className="flex flex-col items-center gap-2">
              <div
                className="w-6 h-6 flex items-center justify-center"
                title={`${statusDetails.text} - ${agentConfig?.llm_model || ""}`}
              >
                <span className={`w-2.5 h-2.5 rounded-full ${statusDetails.dotClass}`} />
              </div>
              <button
                type="button"
                onClick={() => setIsConfigModalOpen(true)}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-400 hover:text-zinc-700 hover:bg-zinc-200/60 transition-colors"
                title="Agent Settings"
                aria-label="Agent Settings"
              >
                <Settings className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={onToggleCollapse}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-400 hover:text-zinc-700 hover:bg-zinc-200/60 transition-colors"
                title="Expand sidebar"
                aria-label="Expand sidebar"
              >
                <PanelLeftOpen className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Modern Configuration Modal Dialog */}
      {isConfigModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="config-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/40 backdrop-blur-xs animate-fade-in"
        >
          <div className="w-full max-w-md bg-white rounded-xl shadow-2xl border border-zinc-200 overflow-hidden animate-slide-in-from-bottom">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-100 bg-zinc-50/50">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center border border-blue-100">
                  <SlidersHorizontal className="w-4 h-4" />
                </div>
                <div>
                  <h3 id="config-modal-title" className="text-sm font-semibold text-zinc-900">
                    Agent Configuration
                  </h3>
                  <p className="text-xs text-zinc-400">Configure LLM provider and MCP transport</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsConfigModalOpen(false);
                  setErrorMsg("");
                }}
                disabled={isSaving}
                className="p-1 rounded-md text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 transition-colors"
                aria-label="Close modal"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Form */}
            <form onSubmit={handleSaveConfig} className="p-5 space-y-4">
              {errorMsg && (
                <div className="p-3 text-xs text-rose-700 bg-rose-50 rounded-lg border border-rose-200 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
                  <span>{errorMsg}</span>
                </div>
              )}

              {/* Provider Select */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700">LLM Provider</label>
                <select
                  value={provider}
                  onChange={(e) => handleProviderChange(e.target.value)}
                  disabled={isSaving}
                  className="w-full px-3 py-2 text-xs bg-zinc-50 hover:bg-zinc-100/60 focus:bg-white border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
                >
                  <option value="gemini">Google Gemini</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                </select>
              </div>

              {/* Model Input */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700">Model Name</label>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={isSaving}
                  placeholder="e.g. gemini-3.5-flash or gpt-4o"
                  className="w-full px-3 py-2 text-xs bg-zinc-50 hover:bg-zinc-100/60 focus:bg-white border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors font-mono"
                />
              </div>

              {/* Transport Mode */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-700">MCP Transport Mode</label>
                <select
                  value={transport}
                  onChange={(e) => setTransport(e.target.value)}
                  disabled={isSaving}
                  className="w-full px-3 py-2 text-xs bg-zinc-50 hover:bg-zinc-100/60 focus:bg-white border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
                >
                  <option value="STDIO">STDIO (Standard Process)</option>
                  <option value="SSE">SSE (Server-Sent Events)</option>
                </select>
              </div>

              {/* SSE URL (if transport is SSE) */}
              {transport.toUpperCase() === "SSE" && (
                <div className="space-y-1.5 animate-fade-in">
                  <label className="text-xs font-semibold text-zinc-700">SSE Endpoint URL</label>
                  <input
                    type="text"
                    value={sseUrl}
                    onChange={(e) => setSseUrl(e.target.value)}
                    disabled={isSaving}
                    placeholder="http://localhost:8000/sse"
                    className="w-full px-3 py-2 text-xs bg-zinc-50 hover:bg-zinc-100/60 focus:bg-white border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors font-mono"
                  />
                </div>
              )}

              {/* Footer Actions */}
              <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-100">
                <button
                  type="button"
                  onClick={() => {
                    setIsConfigModalOpen(false);
                    setErrorMsg("");
                  }}
                  disabled={isSaving}
                  className="px-3.5 py-2 text-xs font-medium text-zinc-600 hover:text-zinc-800 hover:bg-zinc-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 active:scale-98 rounded-lg shadow-xs transition-all disabled:opacity-50"
                >
                  {isSaving ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Saving…</span>
                    </>
                  ) : (
                    <>
                      <Save className="w-3.5 h-3.5" />
                      <span>Save Changes</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}