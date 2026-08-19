"use client";

import React, { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo } from "react";
import {
  Terminal, MessageSquare, RefreshCw, Menu, Database, Sparkles, BarChart3, AlertTriangle,
  Download, Cloud, Monitor, Palette, ShieldCheck, X, ChevronDown, ChevronUp, ChevronLeft, ChevronRight,
  Settings, Send, Mic, Paperclip, MoreHorizontal, Sun, Moon, HelpCircle, User, LogOut,
  Bell, Search, Filter, Grid, List, ArrowRight, ArrowLeft, Maximize, Minimize
} from "lucide-react";
import { useAgent } from "@/hooks/use-agent";
import { Sidebar } from "@/components/sidebar";
import { ChatMessageBubble } from "@/components/chat-message";
import { ChatInput } from "@/components/chat-input";
import { ElicitationModal } from "@/components/elicitation-modal";
import { DashboardManager } from "@/components/dashboard-manager";
import type { AgentConfig, ChatMessage } from "@/types";
import type { ConversationSummary } from "@/components/sidebar";
import "@/styles/globals.css";

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
          dashboard_id: String(current.dashboard_id ?? value.dashboard_id ?? ""),
          project_path: String(current.project_path ?? value.project_path ?? ""),
        };
      } catch { /* tool result may still be streaming */ }
    }
  }
  return null;
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [dashboardManagerOpen, setDashboardManagerOpen] = useState(false);
  const [mobilePanelOpen, setMobilePanelOpen] = useState(false);
  const [dashboardId, setDashboardId] = useState<string>("");
  const [projectPath, setProjectPath] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
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

  useEffect(() => {
    fetchConfig();
    const interval = setInterval(() => { fetchConfig(); }, 3000);
    return () => clearInterval(interval);
  }, [fetchConfig]);

  const handleConfigUpdate = async (newConfig: AgentConfig) => {
    try {
      const res = await fetch(`${backendUrls.http}/api/config`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(newConfig),
      });
      if (res.ok) { const updatedConfig = await res.json(); setAgentConfig(updatedConfig); return true; }
    } catch (err) { console.error("Error updating config:", err); }
    return false;
  };

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
    if (window.innerWidth < 900) setMobileSidebarOpen(false);
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

  const handleMessagesScroll = () => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    isPinnedToBottomRef.current = distanceFromBottom <= 120;
  };

  useLayoutEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const lastMessageIsUser = messages.length > 0 && messages[messages.length - 1].role === "user";
    if (lastMessageIsUser) { isPinnedToBottomRef.current = true; }
    if (isPinnedToBottomRef.current) { container.scrollTop = container.scrollHeight; }
  }, [messages, activeToolCalls]);

  // Update dashboard manager state when dashboard info is available
  useEffect(() => {
    const state = latestDashboardState(messages);
    if (state?.dashboard_id) {
      setDashboardId(state.dashboard_id);
      setProjectPath(state.project_path);
      setDashboardManagerOpen(true);
    }
  }, [messages]);

  const isRunning = agentStatus === "running" || agentStatus === "starting_agent" || agentStatus === "mcp_connected";
  const inputDisabled = connectionStatus !== "connected";
  const dashboardState = latestDashboardState(messages);

  const statusDisplay = () => {
    const statusConfig = {
      idle: null,
      starting_agent: { label: "Preparing analysis…", icon: <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />, className: "bg-zinc-100 text-zinc-700 border-zinc-200" },
      mcp_connected: { label: "Power BI tools ready", icon: <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />, className: "bg-zinc-100 text-zinc-700 border-zinc-200" },
      running: { label: "Analyzing your data…", icon: <RefreshCw className="w-3 h-3 animate-spin text-zinc-500" />, className: "bg-zinc-100 text-zinc-700 border-zinc-200" },
      complete: { label: "Analysis complete", icon: null, className: "bg-zinc-100 text-zinc-700 border-zinc-200" },
      error: { label: "Analysis needs attention", icon: null, className: "bg-red-50 text-red-700 border-red-100" },
    };
    const config = statusConfig[agentStatus as keyof typeof statusConfig];
    if (!config) return null;
    return (
      <div className={`flex items-center gap-2 px-3 py-1 rounded-full border text-xs ${config.className}`}>
        {config.icon}
        <span>{config.label}</span>
      </div>
    );
  };

  const filteredConversations = conversations.filter(c =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className={`workspace ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      {/* Sidebar */}
      <aside className="workspace-sidebar" aria-label="Navigation">
        {/* Sidebar Header */}
        <div className="sidebar-header flex items-center justify-between">
          <div className="sidebar-logo flex items-center gap-3 flex-1 min-w-0">
            <div className="sidebar-logo-icon"><Terminal className="w-6 h-6" /></div>
            {!sidebarCollapsed && <span className="sidebar-logo-text truncate">Power BI Agent</span>}
          </div>
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 transition-colors"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {sidebarCollapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="sidebar-section flex-1 overflow-y-auto" aria-label="Main navigation">
          <h3 className="sidebar-section-title">
            <span>Workspace</span>
          </h3>
          <div className="sidebar-nav">
            <a href="#" className="sidebar-nav-item active" title="Analysis">
              <MessageSquare className="icon w-5 h-5" />
              {!sidebarCollapsed && <span>Analysis</span>}
            </a>
            <a href="#" className="sidebar-nav-item" title="Dashboards">
              <BarChart3 className="icon w-5 h-5" />
              {!sidebarCollapsed && <span>Dashboards</span>}
            </a>
            <a href="#" className="sidebar-nav-item" title="Models">
              <Database className="icon w-5 h-5" />
              {!sidebarCollapsed && <span>Semantic Models</span>}
            </a>
            <a href="#" className="sidebar-nav-item" title="Qualification">
              <ShieldCheck className="icon w-5 h-5" />
              {!sidebarCollapsed && <span>Qualification</span>}
            </a>
          </div>

          {/* Conversations */}
          <h3 className="sidebar-section-title">
            <span>Conversations</span>
            {!sidebarCollapsed && conversations.length > 0 && (
              <span className="badge badge-primary">{conversations.length}</span>
            )}
          </h3>
          <div className="sidebar-nav" style={{ maxHeight: "300px", overflow: "auto" }}>
            {searchQuery && (
              <div className="p-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search conversations..."
                  className="w-full px-3 py-2 text-sm border border-zinc-200 rounded-lg bg-white focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>
            )}
            {filteredConversations.map((conversation) => (
              <button
                key={conversation.id}
                onClick={() => selectConversation(conversation.id)}
                className={`sidebar-nav-item ${activeConversationId === conversation.id ? "active" : ""} text-left w-full`}
                title={conversation.title}
              >
                <MessageSquare className="icon w-5 h-5" />
                {!sidebarCollapsed && (
                  <>
                    <span className="truncate flex-1">{conversation.title}</span>
                    <span className="text-xs text-zinc-400 whitespace-nowrap">
                      {new Date(conversation.updatedAt).toLocaleDateString()}
                    </span>
                  </>
                )}
              </button>
            ))}
            {filteredConversations.length === 0 && conversations.length > 0 && !sidebarCollapsed && (
              <div className="px-3 py-4 text-center text-xs text-zinc-400">No conversations match</div>
            )}
            {!conversations.length && !sidebarCollapsed && (
              <div className="px-3 py-4 text-center text-xs text-zinc-400">No conversations yet</div>
            )}
          </div>
        </nav>

        {/* New Conversation Button */}
        {!sidebarCollapsed && (
          <div className="sidebar-section">
            <button
              onClick={newConversation}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-brand-50 text-brand-700 border border-brand-200 rounded-lg text-sm font-medium hover:bg-brand-100 transition-colors"
            >
              <MessageSquare className="w-4 h-4" />
              <span>New Conversation</span>
            </button>
          </div>
        )}

        {/* Discovered Tools */}
        <div className="sidebar-section">
          <h3 className="sidebar-section-title">
            <span>Discovered Tools</span>
            {discoveredTools.length > 0 && !sidebarCollapsed && (
              <span className="badge badge-primary">{discoveredTools.length}</span>
            )}
          </h3>
          <div className="sidebar-tools">
            {discoveredTools.map((tool) => (
              <span key={tool} className="sidebar-tool-tag" title={tool}>
                {sidebarCollapsed ? tool.split("_").map(w => w[0]).join("") : tool}
              </span>
            ))}
            {!discoveredTools.length && !sidebarCollapsed && (
              <span className="text-xs text-zinc-400 italic w-full text-center py-2">Connect to discover tools</span>
            )}
          </div>
        </div>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className={`sidebar-status-indicator ${connectionStatus}`} />
            {!sidebarCollapsed && (
              <span className="capitalize">
                {connectionStatus === "connected" ? "Connected" :
                 connectionStatus === "connecting" ? "Connecting…" :
                 connectionStatus === "error" ? "Connection Error" : "Disconnected"}
              </span>
            )}
          </div>
          {!sidebarCollapsed && (
            <div className="mt-3 flex items-center gap-2">
              <button className="flex-1 px-3 py-2 text-sm font-medium text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded-lg border border-zinc-200 transition-colors"
                onClick={() => setMobileSidebarOpen(false)}>Close Sidebar</button>
            </div>
          )}
        </div>
      </aside>

      {/* Mobile Sidebar Overlay */}
      {mobileSidebarOpen && (
        <button
          onClick={() => setMobileSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-zinc-950/20 lg:hidden"
          aria-label="Close sidebar"
        />
      )}

      {/* Header */}
      <header className="workspace-header">
        <div className="header-left flex items-center gap-3">
          <button
            onClick={() => setMobileSidebarOpen(true)}
            className="lg:hidden p-2 rounded-lg text-zinc-500 hover:bg-zinc-100"
            aria-label="Open sidebar"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="workspace-breadcrumb">
            <span className="font-medium text-zinc-700">Analysis Workspace</span>
            {dashboardState && (
              <>
                <span className="separator">/</span>
                <span className="font-medium text-zinc-700 truncate max-w-[200px]">{dashboardState.title}</span>
              </>
            )}
          </div>
        </div>

        <div className="header-center">
          {!sidebarCollapsed && (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
              <input
                type="text"
                placeholder="Search workspace… (⌘K)"
                className="w-full max-w-[400px] pl-10 pr-4 py-2 text-sm bg-zinc-50 border border-zinc-200 rounded-lg focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500"
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          )}
        </div>

        <div className="header-right flex items-center gap-2">
          {/* Connection Status */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-50 border border-zinc-200">
            <span className={`sidebar-status-indicator ${connectionStatus}`} style={{width: 6, height: 6}} />
            <span className="text-xs font-medium text-zinc-600 capitalize hidden sm:block">
              {connectionStatus === "connected" ? "Connected" :
               connectionStatus === "connecting" ? "Connecting" :
               connectionStatus === "error" ? "Error" : "Offline"}
            </span>
            {(connectionStatus === "error" || connectionStatus === "disconnected") && (
              <button onClick={reconnect} className="px-2 py-1 text-xs font-medium text-brand-600 hover:text-brand-700">Reconnect</button>
            )}
          </div>

          {/* Reasoning Effort */}
          <div className="hidden sm:flex items-center gap-1 p-0.5 bg-zinc-50 rounded-lg border border-zinc-200">
            {["off", "low", "medium", "high"].map((effort) => (
              <button
                key={effort}
                onClick={() => setReasoningEffort(effort)}
                className={`px-2.5 py-1.5 text-xs font-medium rounded transition-colors capitalize ${
                  reasoningEffort === effort
                    ? "bg-white text-zinc-900 shadow-sm border border-zinc-200"
                    : "text-zinc-500 hover:text-zinc-700"
                }`}
              >
                {effort}
              </button>
            ))}
          </div>

          {/* User Menu */}
          <div className="relative">
            <button
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 transition-colors"
            >
              <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center">
                <Terminal className="w-4 h-4 text-brand-600" />
              </div>
              <span className="hidden sm:block text-sm font-medium">Analyst</span>
              <ChevronDown className="w-4 h-4 text-zinc-400" />
            </button>
          </div>

          {/* Mobile Panel Toggle */}
          {dashboardManagerOpen && window.innerWidth < 1200 && (
            <button
              onClick={() => setMobilePanelOpen(!mobilePanelOpen)}
              className="lg:hidden p-2 rounded-lg text-zinc-500 hover:bg-zinc-100"
              aria-label="Toggle dashboard panel"
            >
              {mobilePanelOpen ? <Minimize className="w-5 h-5" /> : <Maximize className="w-5 h-5" />}
            </button>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className={`workspace-main ${dashboardManagerOpen && dashboardId && projectPath ? "with-panel" : ""}`}>
        {/* Chat Area */}
        <div className="chat-area flex-1 flex flex-col min-w-0">
          {/* Connection Banner */}
          {(connectionStatus === "error" || connectionStatus === "disconnected") && (
            <div className={`px-6 py-3 text-sm flex items-center justify-between gap-3 border-b ${
              connectionStatus === "error" ? "bg-red-50 text-red-800 border-red-100" : "bg-amber-50 text-amber-800 border-amber-100"
            }`} role="status">
              <span className="flex items-center gap-2">
                {connectionStatus === "error" ? <AlertTriangle className="w-4 h-4" /> : <RefreshCw className="w-4 h-4 animate-spin" />}
                {connectionStatus === "error"
                  ? "Power BI connection error. Your conversation is safe; reconnect to continue."
                  : "Connection lost. Reconnecting automatically…"}
              </span>
              {connectionStatus === "error" && (
                <button onClick={reconnect} className="px-3 py-1 text-sm font-semibold text-red-700 hover:text-red-900 bg-white border border-red-200 rounded">Reconnect</button>
              )}
            </div>
          )}

          {/* Dashboard Status Bar */}
          {dashboardState && !dashboardManagerOpen && (
            <div className="px-6 py-3 bg-brand-50 border-b border-brand-100 flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-3">
                <div className="p-1.5 bg-brand-100 rounded-lg"><BarChart3 className="w-4 h-4 text-brand-600" /></div>
                <div>
                  <p className="font-semibold text-zinc-900 text-sm truncate max-w-[300px]">{dashboardState.title}</p>
                  <p className="text-xs text-zinc-500 flex items-center gap-2">
                      {dashboardState.version != null ? (
                        <span className="px-1.5 py-0.5 text-[9px] font-semibold text-indigo-700 bg-indigo-50 rounded border border-indigo-100">
                          v{String(dashboardState.version)}
                        </span>
                      ) : null}
                      <span className={`flex items-center gap-1 ${dashboardState.published ? "text-emerald-600" : "text-amber-600"}`}>
                        <Cloud className="w-3 h-3" />
                        {dashboardState.published ? "Published" : "Not published"}
                      </span>
                      {dashboardState.rendered ? (
                        <span className="flex items-center gap-1 text-blue-600">
                          <ShieldCheck className="w-3 h-3" /> QA Done
                        </span>
                      ) : null}
                    </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => sendQuery("Render the active dashboard and inspect the PNG for layout and color issues.", reasoningEffort)}
                  className="btn btn-secondary btn-sm"><ShieldCheck className="w-3.5 h-3.5" /> Inspect</button>
                <button onClick={() => sendQuery("Revise the active dashboard to improve its visual styling and apply the requested colors, then validate it.", reasoningEffort)}
                  className="btn btn-secondary btn-sm"><Palette className="w-3.5 h-3.5" /> Restyle</button>
                <button onClick={() => setDashboardManagerOpen(true)} className="btn btn-primary btn-sm"><Grid className="w-3.5 h-3.5" /> Open Manager</button>
              </div>
            </div>
          )}

          {/* Messages */}
          <div
            ref={scrollContainerRef}
            onScroll={handleMessagesScroll}
            className="chat-messages"
          >
            {messages.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
                <div className="mb-6 p-4 rounded-2xl bg-brand-50 ring-1 ring-brand-100"><Terminal className="w-10 h-10 text-brand-500" /></div>
                <h2 className="text-2xl font-semibold tracking-tight text-zinc-900 mb-2">What would you like to understand?</h2>
                <p className="text-zinc-500 max-w-lg mb-8">Ask questions about your Power BI data, uncover trends, or create a report from your model.</p>
                <div className="grid w-full max-w-2xl gap-3 sm:grid-cols-3">
                  {[
                    { icon: BarChart3, label: "Analyze performance", prompt: "Analyze my sales performance and highlight the biggest trends." },
                    { icon: Database, label: "Explore my data", prompt: "What tables and measures are available in my model?" },
                    { icon: AlertTriangle, label: "Find anomalies", prompt: "Find unusual changes or anomalies in my latest data." },
                  ].map(({ icon: Icon, label, prompt }) => (
                    <button key={label} onClick={() => sendQuery(prompt, reasoningEffort)} disabled={inputDisabled}
                      className="p-4 text-left rounded-xl border border-zinc-200 bg-white shadow-sm hover:border-brand-300 hover:shadow-md hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed">
                      <Icon className="mb-2 w-5 h-5 text-brand-500" />
                      <span className="text-xs font-semibold text-zinc-800 block mb-1">{label}</span>
                      <p className="text-[11px] text-zinc-400">{prompt}</p>
                    </button>
                  ))}
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

          {/* Input */}
          <div className="chat-input-area">
            <ChatInput
              onSend={(text) => sendQuery(text, reasoningEffort)}
              onAbort={abort}
              disabled={inputDisabled}
              isRunning={isRunning}
              inputRef={inputRef}
            />
          </div>
        </div>

        {/* Right Panel - Dashboard Manager */}
        {dashboardManagerOpen && dashboardId && projectPath && (
          <>
            {/* Mobile Panel Overlay */}
            {window.innerWidth < 1200 && mobilePanelOpen && (
              <button
                onClick={() => setMobilePanelOpen(false)}
                className="fixed inset-0 z-40 bg-zinc-950/30 lg:hidden"
                aria-label="Close panel"
              />
            )}
            <aside
              className={`right-panel ${window.innerWidth < 1200 && mobilePanelOpen ? "open" : ""}`}
              aria-label="Dashboard Manager"
            >
              <div className="panel-header flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => { setDashboardManagerOpen(false); setDashboardId(""); setProjectPath(""); }}
                    className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 transition-colors lg:hidden"
                    aria-label="Close panel"
                  >
                    <X className="w-5 h-5" />
                  </button>
                  <div className="p-1.5 bg-brand-100 rounded-lg"><BarChart3 className="w-5 h-5 text-brand-600" /></div>
                  <div className="min-w-0">
                    <h2 className="panel-title truncate">{dashboardState?.title || "Active Dashboard"}</h2>
                    <p className="text-xs text-zinc-500">{dashboardState?.version != null ? `v${dashboardState.version}` : "Local version"}</p>
                  </div>
                </div>
                <button
                  onClick={() => { setDashboardManagerOpen(false); setDashboardId(""); setProjectPath(""); }}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 transition-colors hidden lg:flex"
                  aria-label="Close panel"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <DashboardManager
                dashboardId={dashboardId}
                projectPath={projectPath}
              />
            </aside>
          </>
        )}

        {/* Mobile Panel Toggle Button */}
        {dashboardManagerOpen && window.innerWidth < 1200 && !mobilePanelOpen && (
          <button
            onClick={() => setMobilePanelOpen(true)}
            className="fixed bottom-6 right-6 z-30 btn btn-primary btn-lg shadow-lg"
            aria-label="Open dashboard panel"
          >
            <Grid className="w-5 h-5" />
          </button>
        )}
      </main>

      {/* Elicitation Modal Overlay */}
      {elicitation && (
        <ElicitationModal
          elicitation={elicitation}
          onRespond={(action, content) => respondToElicitation(elicitation.id, action, content)}
        />
      )}
    </div>
  );
}