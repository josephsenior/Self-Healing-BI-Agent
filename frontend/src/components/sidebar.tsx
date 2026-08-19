"use client";

import React, { useState, useEffect } from "react";
import { Cpu, RefreshCw, Shield, Settings, Save, X, Loader2, MessageSquarePlus, Trash2 } from "lucide-react";
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
}: SidebarProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [transport, setTransport] = useState("");
  const [sseUrl, setSseUrl] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

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
    if (selectedProvider === "gemini") {
      setModel("gemini-3.5-flash");
    } else if (selectedProvider === "openai") {
      setModel("gpt-4o");
    } else if (selectedProvider === "anthropic") {
      setModel("claude-3-5-sonnet-latest");
    }
  };

  const statusDot = () => {
    switch (connectionStatus) {
      case "connected":
        return (
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-orange-500" />
          </span>
        );
      case "connecting":
        return <span className="h-2 w-2 rounded-full bg-zinc-400 animate-pulse" />;
      case "error":
        return <span className="h-2 w-2 rounded-full bg-red-500" />;
      default:
        return <span className="h-2 w-2 rounded-full bg-zinc-300" />;
    }
  };

  const statusText = () => {
    switch (connectionStatus) {
      case "connected":
        return "Connected";
      case "connecting":
        return "Connecting…";
      case "disconnected":
        return "Disconnected";
      case "error":
        return "Connection Error";
    }
  };

  return (
    <>
      {mobileOpen && <button aria-label="Close sidebar" onClick={onCloseMobile} className="fixed inset-0 z-30 bg-zinc-950/20 lg:hidden" />}
      {isEditing && <button aria-label="Close settings" onClick={() => !isSaving && setIsEditing(false)} className="fixed inset-0 z-50 bg-zinc-950/30 backdrop-blur-sm" />}
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-[290px] flex-shrink-0 flex-col justify-between overflow-hidden border-r border-zinc-200 bg-zinc-50 text-zinc-600 shadow-xl transition-transform lg:static lg:z-auto lg:h-screen lg:shadow-none ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
      <div className="p-5 space-y-5 overflow-y-auto flex-1">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="p-2 bg-white text-zinc-900 rounded-lg border border-zinc-200 shadow-sm">
            <Cpu className="w-5 h-5 text-orange-500" />
          </div>
          <div>
            <h1 className="font-semibold text-sm text-zinc-900 tracking-tight">
              Power BI MCP Agent
            </h1>
            <p className="text-[11px] text-zinc-500">Autonomous Data Analysis</p>
          </div>
          <button onClick={onNewConversation} className="ml-auto rounded-lg border border-orange-200 bg-orange-50 p-2 text-orange-600 transition-colors hover:bg-orange-100" title="New conversation" aria-label="New conversation">
            <MessageSquarePlus className="size-4" />
          </button>
        </div>

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">Conversations</h2>
            <button onClick={onNewConversation} className="text-[10px] font-semibold text-orange-600 hover:text-orange-700">New</button>
          </div>
          <div className="space-y-1">
            {conversations.map((conversation) => (
              <div key={conversation.id} className={`group flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-colors ${activeConversationId === conversation.id ? "border-orange-200 bg-white shadow-sm" : "border-transparent hover:border-zinc-200 hover:bg-white/70"}`}>
                <button onClick={() => { onSelectConversation(conversation.id); onCloseMobile(); }} className="min-w-0 flex-1 text-left">
                  <p className="truncate text-xs font-medium text-zinc-800">{conversation.title}</p>
                  <p className="mt-0.5 text-[10px] text-zinc-400">{new Date(conversation.updatedAt).toLocaleDateString()}</p>
                </button>
                {conversations.length > 1 && <button onClick={() => onDeleteConversation(conversation.id)} className="rounded p-1 text-zinc-300 opacity-0 transition-opacity hover:bg-red-50 hover:text-red-500 group-hover:opacity-100" title="Delete conversation" aria-label={`Delete ${conversation.title}`}><Trash2 className="size-3.5" /></button>}
              </div>
            ))}
          </div>
        </section>

        {/* Connection Status */}
        <div role={isEditing ? "dialog" : undefined} aria-modal={isEditing ? true : undefined} aria-label={isEditing ? "Agent settings" : undefined} className={`space-y-2.5 rounded-lg border border-zinc-200 bg-white p-3 shadow-sm ${isEditing ? "fixed inset-x-4 top-1/2 z-[60] mx-auto max-h-[calc(100vh-2rem)] w-auto max-w-lg -translate-y-1/2 overflow-y-auto p-5 shadow-2xl sm:inset-x-auto sm:w-[min(32rem,calc(100vw-2rem))]" : ""}`}>
          <h2 className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
            Connection
          </h2>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {statusDot()}
              <span className="text-xs font-medium text-zinc-800">{statusText()}</span>
            </div>
            {(connectionStatus === "disconnected" || connectionStatus === "error") && (
              <button
                onClick={onReconnect}
                className="rounded-md border border-zinc-200 bg-zinc-50 p-1.5 text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900"
                title="Reconnect"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Configuration */}
        <div className="bg-white rounded-lg p-3 border border-zinc-200 shadow-sm space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
              Settings
            </h2>
            {agentConfig && !isEditing && (
              <button
                onClick={() => setIsEditing(true)}
                className="p-1 text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 rounded transition-colors"
                title="Edit Configuration"
              >
                <Settings className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {agentConfig ? (
            isEditing ? (
              <form onSubmit={handleSave} className="space-y-3 text-[11px]">
                {errorMsg && (
                  <div className="text-[10px] text-red-500 bg-red-50 p-1.5 rounded border border-red-100">
                    {errorMsg}
                  </div>
                )}
                
                <div className="space-y-1">
                  <label className="text-zinc-400 font-medium">LLM Provider</label>
                  <select
                    value={provider}
                    onChange={(e) => selectProviderModelDefault(e.target.value)}
                    disabled={isSaving}
                    className="w-full bg-zinc-50 border border-zinc-200 rounded px-2 py-1 text-zinc-800 focus:outline-none focus:border-orange-500 font-mono text-[11px] h-7"
                  >
                    <option value="gemini">Gemini</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-zinc-400 font-medium">Model</label>
                  <input
                    type="text"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    disabled={isSaving}
                    placeholder="e.g. gpt-4o"
                    className="w-full bg-zinc-50 border border-zinc-200 rounded px-2 py-1 text-zinc-800 focus:outline-none focus:border-orange-500 font-mono text-[11px] h-7"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-zinc-400 font-medium">Transport</label>
                  <select
                    value={transport}
                    onChange={(e) => setTransport(e.target.value)}
                    disabled={isSaving}
                    className="w-full bg-zinc-50 border border-zinc-200 rounded px-2 py-1 text-zinc-800 focus:outline-none focus:border-orange-500 font-mono text-[11px] h-7"
                  >
                    <option value="STDIO">STDIO</option>
                    <option value="SSE">SSE</option>
                  </select>
                </div>

                {transport.toUpperCase() === "SSE" && (
                  <div className="space-y-1">
                    <label className="text-zinc-400 font-medium">SSE URL</label>
                    <input
                      type="text"
                      value={sseUrl}
                      onChange={(e) => setSseUrl(e.target.value)}
                      disabled={isSaving}
                      placeholder="https://..."
                      className="w-full bg-zinc-50 border border-zinc-200 rounded px-2 py-1 text-zinc-800 focus:outline-none focus:border-orange-500 font-mono text-[11px] h-7"
                    />
                  </div>
                )}

                <div className="flex gap-2 pt-1">
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="flex-1 flex items-center justify-center gap-1 bg-orange-500 hover:bg-orange-600 text-white font-medium rounded py-1 text-[10px] transition-colors shadow-sm disabled:opacity-50 h-7"
                  >
                    {isSaving ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <>
                        <Save className="w-3 h-3" />
                        <span>Save</span>
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsEditing(false);
                      setErrorMsg("");
                    }}
                    disabled={isSaving}
                    className="flex-1 flex items-center justify-center gap-1 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 font-medium rounded py-1 text-[10px] border border-zinc-200 transition-colors h-7"
                  >
                    <X className="w-3 h-3" />
                    <span>Cancel</span>
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-zinc-500">LLM Provider</span>
                  <span className="font-mono text-zinc-800 font-medium capitalize">
                    {agentConfig.llm_provider}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Model</span>
                  <span className="font-mono text-zinc-800 font-medium">{agentConfig.llm_model}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Transport</span>
                  <span className="font-mono text-zinc-800 font-medium">{agentConfig.transport_mode}</span>
                </div>
                {agentConfig.transport_mode.toUpperCase() === "SSE" && agentConfig.sse_url && (
                  <div className="flex flex-col gap-0.5 pt-1 border-t border-zinc-100 mt-1">
                    <span className="text-zinc-400">SSE URL</span>
                    <span className="truncate font-mono text-zinc-600 max-w-full text-[10px]" title={agentConfig.sse_url}>
                      {agentConfig.sse_url}
                    </span>
                  </div>
                )}
              </div>
            )
          ) : (
            <p className="text-[11px] text-zinc-400 italic">No config loaded</p>
          )}
        </div>

        {/* Reasoning Effort Switcher */}
        <div className="bg-white rounded-lg p-3 border border-zinc-200 shadow-sm space-y-2.5">
          <h2 className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
            Reasoning Effort
          </h2>
          <div className="grid grid-cols-4 gap-1 p-0.5 bg-zinc-100/80 rounded-lg border border-zinc-200">
            {["off", "low", "medium", "high"].map((effort) => (
              <button
                key={effort}
                type="button"
                onClick={() => onReasoningEffortChange(effort)}
                className={`py-1 text-[10px] font-medium rounded transition-all capitalize ${
                  reasoningEffort === effort
                    ? "bg-white text-zinc-950 shadow-sm border border-zinc-200/50"
                    : "text-zinc-500 hover:text-zinc-800"
                }`}
              >
                {effort}
              </button>
            ))}
          </div>
        </div>

        {/* Discovered Tools */}
        <div className="bg-white rounded-lg p-3 border border-zinc-200 shadow-sm space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
              Discovered Tools
            </h2>
            {discoveredTools.length > 0 && (
              <span className="text-[10px] font-mono bg-orange-50 text-orange-600 px-1.5 py-0.5 rounded-full border border-orange-100 font-medium">
                {discoveredTools.length}
              </span>
            )}
          </div>
          {discoveredTools.length > 0 ? (
            <div className="max-h-40 overflow-y-auto space-y-1">
              {discoveredTools.map((tool) => (
                <span
                  key={tool}
                  className="mr-1 mb-1 inline-block rounded-md border border-zinc-200 bg-zinc-50 px-2 py-0.5 font-mono text-[10px] text-zinc-600"
                >
                  {tool}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-zinc-400 italic">Connect to discover tools</p>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-zinc-200 flex items-center gap-2 text-[10px] text-zinc-400">
        <Shield className="w-3.5 h-3.5 text-orange-500" />
        <span>Enterprise Safety · Human-in-the-Loop</span>
      </div>
    </aside>
    </>
  );
}
