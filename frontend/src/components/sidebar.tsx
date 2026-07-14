"use client";

import React from "react";
import { Cpu, RefreshCw, Shield } from "lucide-react";
import type { ConnectionStatus, AgentConfig } from "@/types";

interface SidebarProps {
  connectionStatus: ConnectionStatus;
  agentConfig: AgentConfig | null;
  discoveredTools: string[];
  onReconnect: () => void;
}

export function Sidebar({
  connectionStatus,
  agentConfig,
  discoveredTools,
  onReconnect,
}: SidebarProps) {
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
          <h2 className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
            Configuration
          </h2>
          {agentConfig ? (
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
            </div>
          ) : (
            <p className="text-[11px] text-zinc-400 italic">No config loaded</p>
          )}
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
