"use client";

import React, { useState, useEffect } from "react";
import { Cpu, RefreshCw, Shield, Settings, Save, X, Loader2 } from "lucide-react";
import type { ConnectionStatus, AgentConfig } from "@/types";

interface SidebarProps {
  connectionStatus: ConnectionStatus;
  agentConfig: AgentConfig | null;
  discoveredTools: string[];
  onReconnect: () => void;
  onConfigUpdate: (newConfig: AgentConfig) => Promise<boolean>;
  reasoningEffort: string;
  onReasoningEffortChange: (val: string) => void;
}

export function Sidebar({
  connectionStatus,
  agentConfig,
  discoveredTools,
  onReconnect,
  onConfigUpdate,
  reasoningEffort,
  onReasoningEffortChange,
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
    <aside className="w-[280px] flex-shrink-0 border-r border-zinc-200 bg-zinc-50 flex flex-col justify-between h-screen overflow-hidden text-zinc-600">
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
        </div>

        {/* Connection Status */}
        <div className="bg-white rounded-lg p-3 border border-zinc-200 shadow-sm space-y-2.5">
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
                className="p-1.5 bg-zinc-50 hover:bg-zinc-100 text-zinc-600 hover:text-zinc-900 rounded-md border border-zinc-205 transition-colors"
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
              Configuration
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
                    <span className="font-mono text-zinc-650 truncate max-w-full text-[10px]" title={agentConfig.sse_url}>
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
                  className="inline-block text-[10px] font-mono bg-zinc-50 text-zinc-650 px-2 py-0.5 rounded-md mr-1 mb-1 border border-zinc-200"
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
  );
}
