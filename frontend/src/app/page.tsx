"use client";

import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from "react";
import { Terminal, MessageSquare, RefreshCw } from "lucide-react";
import { useAgent } from "@/hooks/use-agent";
import { Sidebar } from "@/components/sidebar";
import { ChatMessageBubble } from "@/components/chat-message";
import { ChatInput } from "@/components/chat-input";
import { ElicitationModal } from "@/components/elicitation-modal";
import type { AgentConfig } from "@/types";

export default function Home() {
  const [backendUrls, setBackendUrls] = useState({
    http: "http://localhost:8000",
    ws: "ws://localhost:8000/ws/chat",
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      const hostname = window.location.hostname || "localhost";
      setBackendUrls({
        http: process.env.NEXT_PUBLIC_BACKEND_HTTP_URL ?? `http://${hostname}:8000`,
        ws: process.env.NEXT_PUBLIC_BACKEND_WS_URL ?? `ws://${hostname}:8000/ws/chat`,
      });
    }
  }, []);

  const {
    connectionStatus,
    agentStatus,
    messages,
    activeToolCalls,
    elicitation,
    discoveredTools,
    sendQuery,
    respondToElicitation,
    abort,
    reconnect,
  } = useAgent(backendUrls.ws);

  const [agentConfig, setAgentConfig] = useState<AgentConfig | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState<string>("medium");
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isPinnedToBottomRef = useRef(true);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${backendUrls.http}/api/config`);
      if (res.ok) {
        const data: AgentConfig = await res.json();
        setAgentConfig(data);
      }
    } catch {
      setAgentConfig(null);
    }
  }, [backendUrls.http]);

  // Fetch agent config on mount and retry periodically if missing
  useEffect(() => {
    fetchConfig();
    const interval = setInterval(() => {
      fetchConfig();
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchConfig]);

  const handleConfigUpdate = async (newConfig: AgentConfig) => {
    try {
      const res = await fetch(`${backendUrls.http}/api/config`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(newConfig),
      });
      if (res.ok) {
        const updatedConfig = await res.json();
        setAgentConfig(updatedConfig);
        return true;
      }
    } catch (err) {
      console.error("Error updating config:", err);
    }
    return false;
  };

  // Keep streaming content pinned unless the user intentionally scrolls up.
  const handleMessagesScroll = () => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    isPinnedToBottomRef.current = distanceFromBottom <= 120;
  };

  useLayoutEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const lastMessageIsUser =
      messages.length > 0 && messages[messages.length - 1].role === "user";

    if (lastMessageIsUser) {
      isPinnedToBottomRef.current = true;
    }

    if (isPinnedToBottomRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages, activeToolCalls]);

  const isRunning =
    agentStatus === "running" ||
    agentStatus === "starting_agent" ||
    agentStatus === "mcp_connected";

  const inputDisabled = connectionStatus !== "connected";

  const statusDisplay = () => {
    switch (agentStatus) {
      case "idle":
        return null;
      case "starting_agent":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-zinc-100 rounded-full border border-zinc-200 text-xs text-zinc-700">
            <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />
            <span>Starting Agent</span>
          </div>
        );
      case "mcp_connected":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-zinc-100 rounded-full border border-zinc-200 text-xs text-zinc-700">
            <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />
            <span>MCP Connected</span>
          </div>
        );
      case "running":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-zinc-100 rounded-full border border-zinc-200 text-xs text-zinc-700">
            <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />
            <span>Running</span>
          </div>
        );
      case "complete":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-zinc-100 rounded-full border border-zinc-200 text-xs text-zinc-700">
            <span>Complete</span>
          </div>
        );
      case "error":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-red-50 border border-red-100 text-xs text-red-700">
            <span>Error</span>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white text-zinc-900 font-sans">
      {/* Sidebar */}
      <Sidebar
        connectionStatus={connectionStatus}
        agentConfig={agentConfig}
        discoveredTools={discoveredTools}
        onReconnect={reconnect}
        onConfigUpdate={handleConfigUpdate}
        reasoningEffort={reasoningEffort}
        onReasoningEffortChange={setReasoningEffort}
      />

      {/* Main content area */}
      <div className="flex-1 flex flex-col relative min-w-0 bg-zinc-50/30">
        {/* Top navbar */}
        <div className="h-14 border-b border-zinc-200 bg-white flex items-center px-6 justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-orange-500" />
            <span className="text-sm font-semibold text-zinc-800">Console</span>
          </div>
          {statusDisplay()}
        </div>

        {/* Scrollable messages */}
        <div
          ref={scrollContainerRef}
          onScroll={handleMessagesScroll}
          className="flex-1 overflow-y-auto p-6 space-y-4"
        >
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-zinc-400 space-y-3">
              <MessageSquare className="w-12 h-12 text-zinc-300" />
              <p className="text-sm font-medium text-zinc-700">Start a conversation</p>
              <p className="text-xs text-zinc-400 max-w-xs text-center">
                Ask questions about your Power BI data models, run analyses, or request schema modifications.
              </p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <ChatMessageBubble
                key={msg.id}
                message={msg}
                isStreaming={
                  agentStatus === "running" &&
                  idx === messages.length - 1 &&
                  msg.role === "assistant"
                }
              />
            ))
          )}
        </div>

        <ChatInput
          onSend={(text) => sendQuery(text, reasoningEffort)}
          onAbort={abort}
          disabled={inputDisabled}
          isRunning={isRunning}
        />
      </div>

      {/* Elicitation modal overlay */}
      {elicitation && (
        <ElicitationModal
          elicitation={elicitation}
          onRespond={(action, content) =>
            respondToElicitation(elicitation.id, action, content)
          }
        />
      )}
    </div>
  );
}
