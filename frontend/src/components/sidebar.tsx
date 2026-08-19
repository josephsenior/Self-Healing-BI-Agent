"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Cpu, RefreshCw, Settings, Save, X, Loader2, MessageSquarePlus, Trash2,
  ChevronRight, ChevronLeft, MessageSquare, BarChart3, Database, ShieldCheck,
  Globe, Wifi, WifiOff, AlertCircle, CheckCircle, ExternalLink, Gem
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

const STATUS_CONFIG = {
  connected: { label: "Connected", icon: <CheckCircle className="w-3 h-3" />, className: "text-success-600 bg-success-50", dotClassName: "bg-success-500" },
  connecting: { label: "Connecting…", icon: <RefreshCw className="w-3 h-3 animate-spin" />, className: "text-warning-600 bg-warning-50", dotClassName: "bg-warning-500 animate-pulse" },
  disconnected: { label: "Disconnected", icon: <WifiOff className="w-3 h-3" />, className: "text-zinc-500 bg-zinc-50", dotClassName: "bg-zinc-400" },
  error: { label: "Connection Error", icon: <AlertCircle className="w-3 h-3" />, className: "text-error-600 bg-error-50", dotClassName: "bg-error-500" },
} as const;

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
  const [isEditing, setIsEditing] = useState(false);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [transport, setTransport] = useState("");
  const [sseUrl, setSseUrl] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const statusConfig = STATUS_CONFIG[connectionStatus];

  // Sync form states with agentConfig when entering edit mode or when agentConfig changes
  useEffect(() => {
    if (agentConfig) {
      setProvider(agentConfig.llm_provider);
      setModel(agentConfig.llm_model);
      setTransport(agentConfig.transport_mode);
      setSseUrl(agentConfig.sse_url || "");
    }
  }, [agentConfig, isEditing]);

  useEffect(() => {
    if (!isEditing) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isSaving) {
        setIsEditing(false);
        setErrorMsg("");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isEditing, isSaving]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!provider || !model || !transport) {
      setErrorMsg("All fields are required");
      return;
    }
    if (transport.toUpperCase() === "SSE" && !sseUrl) {
      setErrorMsg("SSE URL is required for SSE transport");
      return;
    }

    setIsSaving(true);
    setErrorMsg("");
    try {
      const success = await onConfigUpdate({
        llm_provider: provider.toLowerCase(),
        llm_model: model,
        transport_mode: transport.toUpperCase(),
        sse_url: transport.toUpperCase() === "SSE" ? sseUrl : null,
      });
      if (success) {
        setIsEditing(false);
      } else {
        setErrorMsg("Failed to update config");
      }
    } catch (err) {
      setErrorMsg("An error occurred while saving");
    } finally {
      setIsSaving(false);
    }
  };

  const selectProviderModelDefault = (selectedProvider: string) => {
    setProvider(selectedProvider);
    setModel(PROVIDER_MODELS[selectedProvider as keyof typeof PROVIDER_MODELS] || "");
  };

  // Conversation item component
  const ConversationItem = React.memo(({ conversation, isActive, onSelect, onDelete }: {
    conversation: ConversationSummary;
    isActive: boolean;
    onSelect: () => void;
    onDelete: () => void;
  }) => (
    <button
      onClick={onSelect}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-left ${
        isActive
          ? "bg-brand-50 border-l-2 border-brand-500"
          : "hover:bg-zinc-100"
      }`}
      title={conversation.title}
    >
      <MessageSquare className={`w-5 h-5 flex-shrink-0 ${isActive ? "text-brand-600" : "text-zinc-400"}`} />
      <div className="min-w-0 flex-1 text-left">
        <p className={`truncate text-sm font-medium ${isActive ? "text-zinc-900" : "text-zinc-700"}`}>
          {conversation.title}
        </p>
        <p className="truncate text-xs text-zinc-500 mt-0.5">
          {new Date(conversation.updatedAt).toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
        </p>
      </div>
      {conversations.length > 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="p-1.5 rounded-lg text-zinc-300 hover:text-error-500 hover:bg-error-50 transition-colors opacity-0 group-hover:opacity-100"
          aria-label={`Delete ${conversation.title}`}
        >
          <Trash2 className="w-4 h-4" />
        </button>
      )}
    </button>
  ));

  // Tool tag component
  const ToolTag = React.memo(({ tool, short }: { tool: string; short: boolean }) => (
    <span className="inline-flex items-center px-2 py-1 text-xs font-mono rounded-md border border-zinc-200 bg-white text-zinc-600 hover:bg-brand-50 hover:border-brand-200 hover:text-brand-700 transition-colors whitespace-nowrap">
      {short ? tool.split("_").map(w => w[0]).join("").toUpperCase() : tool}
    </span>
  ));

  const reasoningOptions = useMemo(() => [
    { value: "off", label: "Off", icon: <X className="w-3.5 h-3.5" /> },
    { value: "low", label: "Low", icon: <MessageSquare className="w-3.5 h-3.5" /> },
    { value: "medium", label: "Med", icon: <MessageSquare className="w-3.5 h-3.5" /> },
    { value: "high", label: "High", icon: <Database className="w-3.5 h-3.5" /> },
  ], []);

  return (
    <>
      {mobileOpen && (
        <button
          aria-label="Close sidebar"
          onClick={onCloseMobile}
          className="fixed inset-0 z-30 bg-zinc-950/20 lg:hidden"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col bg-white border-r border-zinc-200 shadow-xl transition-all duration-200 ease-out lg:static lg:z-auto lg:h-screen lg:shadow-none ${
          mobileOpen ? "translate-x-0 w-[280px]" : collapsed ? "w-[64px] -translate-x-full lg:w-[64px] lg:translate-x-0" : "w-[280px] -translate-x-full lg:w-[280px] lg:translate-x-0"
        }`}
        aria-label="Navigation sidebar"
      >
        {/* Header */}
        <div className="flex items-center justify-between h-14 px-4 border-b border-zinc-200 bg-zinc-50/50 backdrop-blur-sm sticky top-0 z-10">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 bg-brand-100 rounded-lg flex-shrink-0">
              <Gem className="w-5 h-5 text-brand-600" />
            </div>
            {!collapsed && (
              <div className="min-w-0 overflow-hidden">
                <h1 className="font-semibold text-sm text-zinc-900 truncate">Prism</h1>
                <p className="text-xs text-zinc-500 truncate">Intelligence Platform</p>
              </div>
            )}
          </div>
          <button
            onClick={onToggleCollapse}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 transition-colors flex-shrink-0"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto p-4 space-y-6" aria-label="Main navigation">
          {!collapsed && (
            <>
              {/* New Conversation Button */}
              <button
                onClick={onNewConversation}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-brand-50 text-brand-700 border border-brand-200 rounded-lg text-sm font-medium hover:bg-brand-100 hover:border-brand-300 transition-colors"
              >
                <MessageSquarePlus className="w-4 h-4" />
                <span>New Conversation</span>
              </button>

              {/* Conversations */}
              <section aria-labelledby="conversations-heading">
                <div className="flex items-center justify-between mb-2">
                  <h2 id="conversations-heading" className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                    Conversations
                  </h2>
                  {conversations.length > 0 && (
                    <span className="text-xs font-mono text-zinc-400">{conversations.length}</span>
                  )}
                </div>
                <div className="space-y-1" role="listbox">
                  {conversations.map((conversation) => (
                    <ConversationItem
                      key={conversation.id}
                      conversation={conversation}
                      isActive={activeConversationId === conversation.id}
                      onSelect={() => { onSelectConversation(conversation.id); onCloseMobile(); }}
                      onDelete={() => onDeleteConversation(conversation.id)}
                    />
                  ))}
                  {!conversations.length && (
                    <div className="px-3 py-4 text-center text-xs text-zinc-400">
                      No conversations yet
                    </div>
                  )}
                </div>
              </section>
            </>
          )}

          {collapsed && (
            <div className="space-y-1">
              <button
                onClick={onNewConversation}
                className="mx-auto p-2 rounded-lg text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100 transition-colors"
                aria-label="New conversation"
              >
                <MessageSquarePlus className="w-5 h-5" />
              </button>
              {conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  onClick={() => { onSelectConversation(conversation.id); onCloseMobile(); }}
                  className={`mx-auto p-2 rounded-lg transition-colors ${
                    activeConversationId === conversation.id
                      ? "bg-brand-50 text-brand-600"
                      : "text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100"
                  }`}
                  title={conversation.title}
                  aria-label={conversation.title}
                  aria-pressed={activeConversationId === conversation.id}
                >
                  <MessageSquare className="w-5 h-5" />
                </button>
              ))}
            </div>
          )}

          {/* Quick Navigation (collapsed only) */}
          {collapsed && (
            <div className="pt-4 border-t border-zinc-200 space-y-1" role="navigation" aria-label="Quick navigation">
              {[
                { icon: MessageSquare, label: "Analysis", href: "#" },
                { icon: BarChart3, label: "Dashboards", href: "#" },
                { icon: Database, label: "Models", href: "#" },
                { icon: ShieldCheck, label: "Qualification", href: "#" },
              ].map((item) => (
                <a
                  key={item.label}
                  href={item.href}
                  className="mx-auto p-2 rounded-lg text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 transition-colors"
                  aria-label={item.label}
                  title={item.label}
                >
                  <item.icon className="w-5 h-5" />
                </a>
              ))}
            </div>
          )}
        </nav>

        {/* Connection Status & Settings */}
        <div className="p-4 space-y-4 border-t border-zinc-200 bg-zinc-50/50">
          {/* Connection Status */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <div className={`w-2.5 h-2.5 rounded-full ${statusConfig.dotClassName} flex-shrink-0`} />
              {!collapsed && (
                <div className="min-w-0">
                  <p className={`text-sm font-medium ${statusConfig.className.replace("bg-success-50", "").replace("bg-warning-50", "").replace("bg-zinc-50", "").replace("bg-error-50", "")}`}>
                    {statusConfig.label}
                  </p>
                  <p className="text-xs text-zinc-500 truncate">
                    {connectionStatus === "connected" && agentConfig
                      ? `${PROVIDER_LABELS[agentConfig.llm_provider] || agentConfig.llm_provider} · ${agentConfig.llm_model}`
                      : "No active connection"}
                  </p>
                </div>
              )}
            </div>
            {(connectionStatus === "disconnected" || connectionStatus === "error") && !collapsed && (
              <button
                onClick={onReconnect}
                className="p-2 rounded-lg text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100 transition-colors"
                title="Reconnect"
                aria-label="Reconnect"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Settings / Config */}
          {!collapsed && agentConfig && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Configuration</h3>
                <button
                  onClick={() => setIsEditing(true)}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 transition-colors"
                  aria-label="Edit configuration"
                >
                  <Settings className="w-4 h-4" />
                </button>
              </div>

              {isEditing ? (
                <form onSubmit={handleSave} className="space-y-4">
                  {errorMsg && (
                    <div className="p-2 text-xs text-error-600 bg-error-50 rounded border border-error-100">
                      {errorMsg}
                    </div>
                  )}

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-zinc-600">LLM Provider</label>
                    <select
                      value={provider}
                      onChange={(e) => selectProviderModelDefault(e.target.value)}
                      disabled={isSaving}
                      className="w-full px-3 py-2 text-sm bg-white border border-zinc-200 rounded-lg focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 disabled:opacity-50"
                    >
                      <option value="gemini">Google Gemini</option>
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-zinc-600">Model</label>
                    <input
                      type="text"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      disabled={isSaving}
                      placeholder="e.g. gpt-4o"
                      className="w-full px-3 py-2 text-sm bg-white border border-zinc-200 rounded-lg focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 disabled:opacity-50"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-zinc-600">Transport</label>
                    <select
                      value={transport}
                      onChange={(e) => setTransport(e.target.value)}
                      disabled={isSaving}
                      className="w-full px-3 py-2 text-sm bg-white border border-zinc-200 rounded-lg focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 disabled:opacity-50"
                    >
                      <option value="STDIO">STDIO</option>
                      <option value="SSE">SSE</option>
                    </select>
                  </div>

                  {transport.toUpperCase() === "SSE" && (
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-zinc-600">SSE URL</label>
                      <input
                        type="text"
                        value={sseUrl}
                        onChange={(e) => setSseUrl(e.target.value)}
                        disabled={isSaving}
                        placeholder="https://..."
                        className="w-full px-3 py-2 text-sm bg-white border border-zinc-200 rounded-lg focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 disabled:opacity-50"
                      />
                    </div>
                  )}

                  <div className="flex gap-2 pt-2">
                    <button
                      type="submit"
                      disabled={isSaving}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-50"
                    >
                      {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <> <Save className="w-4 h-4" /> <span>Save</span> </>}
                    </button>
                    <button
                      type="button"
                      onClick={() => { setIsEditing(false); setErrorMsg(""); }}
                      disabled={isSaving}
                      className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-zinc-100 text-zinc-700 text-sm font-medium rounded-lg border border-zinc-200 hover:bg-zinc-200 transition-colors"
                    >
                      <X className="w-4 h-4" />
                      <span>Cancel</span>
                    </button>
                  </div>
                </form>
              ) : (
                <div className="space-y-3 text-sm">
                  <div className="flex items-center justify-between py-2 px-3 bg-white border border-zinc-200 rounded-lg">
                    <span className="text-zinc-500">Provider</span>
                    <span className="font-mono font-medium text-zinc-900 capitalize">{PROVIDER_LABELS[agentConfig.llm_provider] || agentConfig.llm_provider}</span>
                  </div>
                  <div className="flex items-center justify-between py-2 px-3 bg-white border border-zinc-200 rounded-lg">
                    <span className="text-zinc-500">Model</span>
                    <span className="font-mono font-medium text-zinc-900 truncate max-w-[140px]">{agentConfig.llm_model}</span>
                  </div>
                  <div className="flex items-center justify-between py-2 px-3 bg-white border border-zinc-200 rounded-lg">
                    <span className="text-zinc-500">Transport</span>
                    <span className="font-mono font-medium text-zinc-900">{agentConfig.transport_mode}</span>
                  </div>
                  {agentConfig.transport_mode.toUpperCase() === "SSE" && agentConfig.sse_url && (
                    <div className="pt-2 border-t border-zinc-100">
                      <div className="flex items-center justify-between py-2 px-3 bg-white border border-zinc-200 rounded-lg">
                        <span className="text-zinc-500">SSE URL</span>
                        <span className="font-mono text-xs text-zinc-600 truncate max-w-[140px]" title={agentConfig.sse_url}>{agentConfig.sse_url}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Reasoning Effort */}
          {!collapsed && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Reasoning Effort</h3>
              <div className="grid grid-cols-4 gap-1.5">
                {reasoningOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => onReasoningEffortChange(opt.value)}
                    className={`py-2 px-3 rounded-lg text-xs font-medium transition-all capitalize ${
                      reasoningEffort === opt.value
                        ? "bg-white text-zinc-900 shadow-sm border border-zinc-200"
                        : "text-zinc-500 hover:text-zinc-700 hover:bg-zinc-50"
                    }`}
                  >
                    {opt.icon}
                    <span className="hidden sm:inline ml-1">{opt.label}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Discovered Tools */}
          {!collapsed && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Discovered Tools</h3>
              {discoveredTools.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {discoveredTools.map((tool) => (
                    <ToolTag key={tool} tool={tool} short={false} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-zinc-400 italic">Connect to discover tools</p>
              )}
            </div>
          )}

          {/* Footer */}
          <div className="pt-4 border-t border-zinc-200 flex items-center gap-2 text-xs text-zinc-400">
            <ShieldCheck className="w-3.5 h-3.5 text-brand-500" />
            {!collapsed && <span>Enterprise Safety · Human-in-the-Loop</span>}
          </div>
        </div>
      </aside>
    </>
  );
}