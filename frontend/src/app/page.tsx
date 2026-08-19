"use client";

import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from "react";
import { Terminal, MessageSquare, RefreshCw, Menu, Database, Sparkles, BarChart3, AlertTriangle, Download, Cloud, Monitor, Palette, ShieldCheck } from "lucide-react";
import { useAgent } from "@/hooks/use-agent";
import { Sidebar } from "@/components/sidebar";
import { ChatMessageBubble } from "@/components/chat-message";
import { ChatInput } from "@/components/chat-input";
import { ElicitationModal } from "@/components/elicitation-modal";
import type { AgentConfig, ChatMessage } from "@/types";
import type { ConversationSummary } from "@/components/sidebar";

type StoredConversation = ConversationSummary & { messages: ChatMessage[] };
const CONVERSATIONS_KEY = "data-analysis-agent-conversations";

function latestDashboardState(messages: ChatMessage[]) {
  for (const message of [...messages].reverse()) {
    for (const part of [...(message.parts ?? [])].reverse()) {
      if (part.type !== "tool_call") continue;
      if (!["get_active_dashboard", "create_dashboard_workspace", "revise_active_dashboard", "publish_pbir_to_fabric", "render_powerbi_report"].includes(part.toolCall.name)) continue;
      if (!part.toolCall.result) continue;
      try {
        const value = JSON.parse(part.toolCall.result) as Record<string, unknown>;
        const current = (value.current as Record<string, unknown> | undefined) ?? value;
        return {
          title: String(current.title ?? current.display_name ?? value.display_name ?? current.dashboard_id ?? value.dashboard_id ?? "Active dashboard"),
          version: current.version ?? value.version,
          published: part.toolCall.name === "publish_pbir_to_fabric" || Boolean(current.published),
          rendered: part.toolCall.name === "render_powerbi_report" || Boolean(current.rendered),
        };
      } catch { /* tool result may still be streaming */ }
    }
  }
  return null;
}

function ArtifactStatusBar({ state, onAction }: { state: ReturnType<typeof latestDashboardState>; onAction: (prompt: string) => void }) {
  if (!state) return null;
  return (
    <div className="border-b border-indigo-100 bg-indigo-50/70 px-4 py-2.5 sm:px-6">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2.5">
        <BarChart3 className="size-4 text-indigo-600" />
        <span className="max-w-56 truncate text-xs font-bold text-indigo-950">{state.title}</span>
        {state.version != null && <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold text-indigo-700 ring-1 ring-indigo-200">v{String(state.version)}</span>}
        <span className="ml-auto flex items-center gap-1.5 text-[10px] text-indigo-700"><Monitor className="size-3" /> Local version</span>
        <span className={`flex items-center gap-1.5 text-[10px] ${state.published ? "text-emerald-700" : "text-amber-700"}`}><Cloud className="size-3" />{state.published ? "Published" : "Not published"}</span>
        <div className="flex items-center gap-1">
          <button onClick={() => onAction("Render the active dashboard and inspect the PNG for layout and color issues.")} className="rounded-md bg-white px-2 py-1 text-[10px] font-semibold text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-100"><ShieldCheck className="mr-1 inline size-3" />Inspect</button>
          <button onClick={() => onAction("Revise the active dashboard to improve its visual styling and apply the requested colors, then validate it.")} className="rounded-md bg-white px-2 py-1 text-[10px] font-semibold text-indigo-700 ring-1 ring-indigo-200 hover:bg-indigo-100"><Palette className="mr-1 inline size-3" />Restyle</button>
        </div>
      </div>
    </div>
  );
}

function restoreMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((message) => ({ ...message, timestamp: new Date(message.timestamp) }));
}

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
    loadConversation,
    clearConversation,
  } = useAgent(backendUrls.ws);

  const [agentConfig, setAgentConfig] = useState<AgentConfig | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState<string>("medium");
  const [conversations, setConversations] = useState<StoredConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const hydratedConversations = useRef(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isPinnedToBottomRef = useRef(true);

  useEffect(() => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(CONVERSATIONS_KEY) || "[]") as StoredConversation[];
      const valid = stored.filter((conversation) => conversation?.id && Array.isArray(conversation.messages));
      const initial = valid.length ? valid : [{ id: crypto.randomUUID(), title: "New conversation", updatedAt: new Date().toISOString(), messages: [] }];
      setConversations(initial);
      setActiveConversationId(initial[0].id);
      loadConversation(initial[0].id, restoreMessages(initial[0].messages));
    } catch {
      const id = crypto.randomUUID();
      setConversations([{ id, title: "New conversation", updatedAt: new Date().toISOString(), messages: [] }]);
      setActiveConversationId(id);
      loadConversation(id, []);
    } finally {
      hydratedConversations.current = true;
    }
  }, [loadConversation]);

  useEffect(() => {
    if (!hydratedConversations.current || !activeConversationId) return;
    const timer = window.setTimeout(() => {
      setConversations((current) => current.map((conversation) => conversation.id === activeConversationId
        ? {
            ...conversation,
            messages,
            updatedAt: messages.length ? new Date().toISOString() : conversation.updatedAt,
            title: conversation.title === "New conversation" && messages.some((message) => message.role === "user")
              ? messages.find((message) => message.role === "user")!.content.slice(0, 38) || "New conversation"
              : conversation.title,
          }
        : conversation));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [messages, activeConversationId]);

  useEffect(() => {
    if (hydratedConversations.current && conversations.length) {
      window.localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
    }
  }, [conversations]);

  const newConversation = () => {
    const conversation = { id: crypto.randomUUID(), title: "New conversation", updatedAt: new Date().toISOString(), messages: [] };
    setConversations((current) => [conversation, ...current]);
    setActiveConversationId(conversation.id);
    clearConversation();
  };

  const selectConversation = (id: string) => {
    const conversation = conversations.find((item) => item.id === id);
    if (!conversation) return;
    setActiveConversationId(id);
    loadConversation(id, restoreMessages(conversation.messages));
  };

  const deleteConversation = (id: string) => {
    if (conversations.length <= 1) return;
    const remaining = conversations.filter((conversation) => conversation.id !== id);
    setConversations(remaining);
    if (id === activeConversationId) {
      setActiveConversationId(remaining[0].id);
      loadConversation(remaining[0].id, restoreMessages(remaining[0].messages));
    }
  };

  const exportConversation = () => {
    const conversation = conversations.find((item) => item.id === activeConversationId);
    if (!conversation) return;
    const content = conversation.messages.map((message) => {
      const label = message.role === "user" ? "You" : "Agent";
      return `${label}\n${message.content}\n`;
    }).join("\n");
    const blob = new Blob([`${conversation.title}\n\n${content}`], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${conversation.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "conversation"}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

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
  const dashboardState = latestDashboardState(messages);

  const statusDisplay = () => {
    switch (agentStatus) {
      case "idle":
        return null;
      case "starting_agent":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-zinc-100 rounded-full border border-zinc-200 text-xs text-zinc-700">
            <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />
            <span>Preparing analysis…</span>
          </div>
        );
      case "mcp_connected":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-zinc-100 rounded-full border border-zinc-200 text-xs text-zinc-700">
            <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />
            <span>Power BI tools ready</span>
          </div>
        );
      case "running":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-zinc-100 rounded-full border border-zinc-200 text-xs text-zinc-700">
            <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />
            <span>Analyzing your data…</span>
          </div>
        );
      case "complete":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-zinc-100 rounded-full border border-zinc-200 text-xs text-zinc-700">
            <span>Analysis complete</span>
          </div>
        );
      case "error":
        return (
          <div className="flex items-center gap-2 px-3 py-1 bg-red-50 border border-red-100 text-xs text-red-700">
            <span>Analysis needs attention</span>
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
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={selectConversation}
        onNewConversation={newConversation}
        onDeleteConversation={deleteConversation}
        mobileOpen={mobileSidebarOpen}
        onCloseMobile={() => setMobileSidebarOpen(false)}
      />

      {/* Main content area */}
      <div className="flex-1 flex flex-col relative min-w-0 bg-zinc-50/30">
        {/* Top navbar */}
        <div className="h-14 border-b border-zinc-200 bg-white flex items-center px-4 sm:px-6 justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <button onClick={() => setMobileSidebarOpen(true)} className="mr-1 rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 lg:hidden" aria-label="Open sidebar"><Menu className="size-4" /></button>
            <Terminal className="w-4 h-4 text-orange-500" />
            <span className="text-sm font-semibold text-zinc-800">Analysis workspace</span>
          </div>
          <div className="flex items-center gap-2">
            {agentConfig && <span className="hidden max-w-52 items-center gap-1.5 truncate rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-[10px] font-medium text-zinc-600 sm:flex"><Database className="size-3 text-orange-500" />{agentConfig.llm_provider} · {agentConfig.llm_model}</span>}
            <button onClick={exportConversation} disabled={!messages.length} className="hidden items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-[10px] font-semibold text-zinc-600 transition-colors hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-40 sm:flex" title="Export conversation"><Download className="size-3.5" />Export</button>
            {statusDisplay()}
          </div>
        </div>

        {(connectionStatus === "error" || connectionStatus === "disconnected") && (
          <div className={`flex items-center justify-between gap-3 border-b px-4 py-2.5 text-xs sm:px-6 ${connectionStatus === "error" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-800"}`} role="status">
            <span>{connectionStatus === "error" ? "Power BI connection error. Your conversation is safe; reconnect to continue." : "Connection lost. Reconnecting automatically…"}</span>
            {connectionStatus === "error" && <button onClick={reconnect} className="rounded-md border border-current/20 bg-white/70 px-2.5 py-1 font-semibold hover:bg-white">Reconnect</button>}
          </div>
        )}

        <ArtifactStatusBar state={dashboardState} onAction={(prompt) => sendQuery(prompt, reasoningEffort)} />

        {/* Scrollable messages */}
        <div
          ref={scrollContainerRef}
          onScroll={handleMessagesScroll}
          className="flex-1 overflow-y-auto p-6 space-y-4"
        >
          {messages.length === 0 ? (
            <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center px-4 py-10 text-center">
              <div className="mb-5 grid size-16 place-items-center rounded-2xl bg-orange-50 text-orange-500 ring-1 ring-orange-100"><Sparkles className="size-7" /></div>
              <p className="text-2xl font-semibold tracking-tight text-zinc-900">What would you like to understand?</p>
              <p className="mt-2 max-w-lg text-sm leading-relaxed text-zinc-500">Ask questions about your Power BI data, uncover trends, or create a report from your model.</p>
              <div className="mt-8 grid w-full max-w-2xl gap-3 sm:grid-cols-3">
                {[{ icon: BarChart3, label: "Analyze performance", prompt: "Analyze my sales performance and highlight the biggest trends." }, { icon: Database, label: "Explore my data", prompt: "What tables and measures are available in my model?" }, { icon: AlertTriangle, label: "Find anomalies", prompt: "Find unusual changes or anomalies in my latest data." }].map(({ icon: Icon, label, prompt }) => <button key={label} onClick={() => sendQuery(prompt, reasoningEffort)} disabled={inputDisabled} className="rounded-xl border border-zinc-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-orange-300 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50"><Icon className="mb-3 size-4 text-orange-500" /><span className="text-xs font-semibold text-zinc-800">{label}</span><p className="mt-1 text-[11px] leading-relaxed text-zinc-400">{prompt}</p></button>)}
              </div>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <ChatMessageBubble
                key={msg.id}
                message={msg}
                onRetry={(text) => sendQuery(text, reasoningEffort)}
                apiBase={backendUrls.http}
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
          inputRef={inputRef}
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
