"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Send,
  Play,
  StopCircle,
  CheckCircle,
  AlertTriangle,
  Link as LinkIcon,
  Cpu,
  Database,
  Sparkles,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  MessageSquare,
  Terminal,
  Activity
} from "lucide-react";

interface ToolCall {
  id: string;
  name: string;
  arguments: any;
  result?: string;
  error?: string;
}

interface Message {
  role: "user" | "assistant";
  content?: string;
  toolCalls?: ToolCall[];
  status?: string;
}

interface ElicitationRequest {
  id: string;
  mode: "form" | "url";
  message: string;
  schema?: {
    properties?: Record<string, any>;
    required?: string[];
    [key: string]: any;
  };
  url?: string;
}

export default function Home() {
  const [socketUrl, setSocketUrl] = useState("ws://localhost:8000/ws/chat");
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<string>("idle");
  const [currentToolCalls, setCurrentToolCalls] = useState<ToolCall[]>([]);
  const [elicitation, setElicitation] = useState<ElicitationRequest | null>(null);
  const [elicitFormData, setElicitFormData] = useState<Record<string, any>>({});
  const [backendHealth, setBackendHealth] = useState<any>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Check backend API health on startup
  useEffect(() => {
    fetch("http://localhost:8000/api/health")
      .then((res) => res.json())
      .then((data) => setBackendHealth(data))
      .catch(() => setBackendHealth({ status: "offline" }));
  }, []);

  // Connect / Disconnect WebSocket
  const connectWebSocket = () => {
    if (socketRef.current) {
      socketRef.current.close();
    }

    const ws = new WebSocket(socketUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setStatus("ready");
    };

    ws.onclose = () => {
      setIsConnected(false);
      setStatus("disconnected");
    };

    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      handleIncomingMessage(payload);
    };
  };

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [socketUrl]);

  // Scroll chat messages to bottom on update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentToolCalls, elicitation]);

  const handleIncomingMessage = (payload: any) => {
    const { type } = payload;

    switch (type) {
      case "status":
        setStatus(payload.status);
        if (payload.status === "starting_agent") {
          setCurrentToolCalls([]);
        }
        break;

      case "token":
        // Append token to the last assistant message
        setMessages((prev) => {
          if (prev.length === 0 || prev[prev.length - 1].role !== "assistant") {
            return [...prev, { role: "assistant", content: payload.text }];
          } else {
            const updated = [...prev];
            const lastMsg = updated[updated.length - 1];
            lastMsg.content = (lastMsg.content || "") + payload.text;
            return updated;
          }
        });
        break;

      case "tool_start":
        // Store incoming tool executions
        const startedCalls = payload.calls.map((c: any) => ({
          id: c.id,
          name: c.name,
          arguments: c.arguments
        }));
        setCurrentToolCalls((prev) => [...prev, ...startedCalls]);
        break;

      case "tool_result":
        // Mark tool execution completed/failed
        setCurrentToolCalls((prev) =>
          prev.map((c) =>
            c.id === payload.id
              ? {
                  ...c,
                  result: payload.result,
                  error: payload.error
                }
              : c
          )
        );
        break;

      case "elicitation_request":
        // Set the active elicitation dialog state
        setElicitation({
          id: payload.id,
          mode: payload.mode,
          message: payload.message,
          schema: payload.schema,
          url: payload.url
        });
        // Pre-fill form data
        const initialForm: Record<string, any> = {};
        if (payload.schema?.properties) {
          Object.keys(payload.schema.properties).forEach((k) => {
            initialForm[k] = payload.schema.properties[k].default ?? "";
          });
        }
        setElicitFormData(initialForm);
        break;

      case "complete":
        setStatus("ready");
        // Flush active tools into the message history object
        setMessages((prev) => {
          if (prev.length > 0 && prev[prev.length - 1].role === "assistant") {
            const updated = [...prev];
            updated[updated.length - 1].toolCalls = [...currentToolCalls];
            return updated;
          }
          return prev;
        });
        setCurrentToolCalls([]);
        break;

      case "error":
        setStatus("error");
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `System Error: ${payload.message}` }
        ]);
        break;

      default:
        break;
    }
  };

  const handleSend = () => {
    if (!input.trim() || !isConnected) return;

    // Send query request to WebSocket
    socketRef.current?.send(
      JSON.stringify({
        type: "query",
        text: input
      })
    );

    // Save prompt to state
    setMessages((prev) => [...prev, { role: "user", content: input }]);
    setInput("");
  };

  const handleAbort = () => {
    socketRef.current?.send(JSON.stringify({ type: "abort" }));
  };

  const handleElicitSubmit = (action: "accept" | "decline" | "cancel") => {
    if (!elicitation) return;

    // Prepare content format based on elicitation inputs
    let responseContent: any = {};
    if (elicitation.mode === "form" && action === "accept") {
      responseContent = { ...elicitFormData };
    }

    // Return decision to backend WebSocket
    socketRef.current?.send(
      JSON.stringify({
        type: "elicitation_response",
        id: elicitation.id,
        action: action,
        content: responseContent
      })
    );

    setElicitation(null);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0b0f19] text-slate-100">
      
      {/* Sidebar - Control Hub */}
      <div className="w-80 flex-shrink-0 border-r border-slate-800 bg-[#0e1322] flex flex-col p-6 justify-between">
        <div className="space-y-6">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-blue-600/20 text-blue-500 rounded-xl border border-blue-500/30">
              <Cpu className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <h1 className="font-bold text-lg text-slate-100 tracking-wide">Power BI MCP</h1>
              <p className="text-xs text-slate-400">Autonomous AI Agent Hub</p>
            </div>
          </div>

          {/* Connection Status */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-3">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">WebSocket Settings</h2>
            <div className="flex items-center space-x-2">
              <span className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-emerald-500" : "bg-rose-500"} animate-pulse`} />
              <span className="text-sm font-medium">{isConnected ? "Connected" : "Disconnected"}</span>
            </div>
            <div className="flex space-x-2">
              <input
                type="text"
                value={socketUrl}
                onChange={(e) => setSocketUrl(e.target.value)}
                className="w-full text-xs bg-slate-950 border border-slate-800 rounded-lg p-2 text-slate-300 focus:outline-none focus:border-blue-500"
              />
              <button
                onClick={connectWebSocket}
                className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition"
                title="Reconnect"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Connected Server Meta */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-3">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Agent Details</h2>
            <div className="space-y-2 text-xs text-slate-300">
              <div className="flex justify-between">
                <span>LLM Provider:</span>
                <span className="font-semibold text-blue-400 capitalize">{backendHealth?.llm_provider ?? "Connecting..."}</span>
              </div>
              <div className="flex justify-between">
                <span>Transport Mode:</span>
                <span className="font-semibold text-purple-400">{backendHealth?.transport_mode ?? "Connecting..."}</span>
              </div>
              <div className="flex justify-between">
                <span>Backend Status:</span>
                <span className={`font-semibold ${backendHealth?.status === "healthy" ? "text-emerald-400" : "text-rose-400"}`}>
                  {backendHealth?.status ?? "Offline"}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="text-[10px] text-slate-500 border-t border-slate-800/80 pt-4 flex justify-between">
          <span>Enterprise Safety Enabled</span>
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col relative bg-[#0b0f19]">
        
        {/* Top Navbar */}
        <div className="h-16 border-b border-slate-800/80 bg-[#0e1322]/40 backdrop-blur-md flex items-center px-8 justify-between">
          <div className="flex items-center space-x-2">
            <Terminal className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-semibold text-slate-300">Interactive Execution Console</span>
          </div>

          {/* Current execution state flag */}
          {status !== "ready" && status !== "idle" && (
            <div className="flex items-center space-x-2 px-3 py-1 bg-blue-500/10 rounded-full border border-blue-500/20 text-xs text-blue-400">
              <RefreshCw className="w-3 h-3 animate-spin" />
              <span className="capitalize">{status.replace("_", " ")}</span>
            </div>
          )}
        </div>

        {/* Messages Stream */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-500 space-y-3">
              <MessageSquare className="w-12 h-12 text-slate-600 animate-bounce" />
              <p className="text-sm">Submit a query to start interacting with your Power BI models</p>
            </div>
          ) : (
            messages.map((msg, index) => (
              <div
                key={index}
                className={`flex w-full ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[75%] rounded-2xl p-5 border text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-blue-600/10 border-blue-500/30 text-slate-100"
                      : "bg-[#111827]/70 border-slate-800/85 text-slate-200"
                  }`}
                >
                  <div className="font-semibold text-xs text-slate-400 mb-2">
                    {msg.role === "user" ? "You" : "AI Agent"}
                  </div>
                  <div className="whitespace-pre-wrap">{msg.content}</div>

                  {/* Render historical tool calls nested in messages */}
                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-slate-800/80 space-y-2">
                      <h4 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center space-x-1.5">
                        <Activity className="w-3.5 h-3.5 text-blue-500" />
                        <span>MCP Server Actions executed:</span>
                      </h4>
                      {msg.toolCalls.map((tc, idx) => (
                        <ToolCallCard key={idx} tc={tc} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {/* Active executing tool calls (streaming logs) */}
          {currentToolCalls.length > 0 && (
            <div className="flex justify-start w-full">
              <div className="max-w-[75%] rounded-2xl p-5 bg-[#111827]/70 border border-slate-800/85 text-slate-200 space-y-3">
                <div className="font-semibold text-xs text-slate-400 mb-1">Active Tool Execution logs:</div>
                {currentToolCalls.map((tc, idx) => (
                  <ToolCallCard key={idx} tc={tc} />
                ))}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-6 border-t border-slate-800/80 bg-[#0e1322]/20 backdrop-blur-md">
          <div className="flex space-x-3 items-center">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              disabled={status !== "ready" && status !== "idle" && status !== "disconnected"}
              placeholder="Ask a question or request a model schema modification..."
              className="flex-1 bg-slate-900 border border-slate-800 focus:border-blue-500 rounded-xl px-5 py-3.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none transition"
            />
            {status !== "ready" && status !== "idle" && status !== "disconnected" ? (
              <button
                onClick={handleAbort}
                className="px-5 py-3.5 bg-rose-600/20 hover:bg-rose-600/35 border border-rose-500/30 text-rose-400 rounded-xl transition flex items-center space-x-2"
              >
                <StopCircle className="w-5 h-5" />
                <span className="text-sm font-semibold">Abort</span>
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!isConnected || !input.trim()}
                className="px-5 py-3.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500 disabled:border-slate-800 rounded-xl transition flex items-center space-x-2 border border-blue-500/30 font-semibold"
              >
                <Send className="w-4 h-4" />
                <span className="text-sm">Run</span>
              </button>
            )}
          </div>
        </div>

        {/* Interactive Elicitation Approval Modal Overlay */}
        {elicitation && (
          <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-6 z-50 animate-fadeIn">
            <div className="w-full max-w-lg rounded-2xl bg-[#0e1322] border border-slate-800 p-6 space-y-6 shadow-2xl shadow-blue-900/10">
              <div className="flex items-center space-x-3 text-amber-500 border-b border-slate-800 pb-4">
                <ShieldCheck className="w-6 h-6 text-blue-400 animate-pulse" />
                <div>
                  <h3 className="font-bold text-slate-100 text-base">Human Approval Required</h3>
                  <p className="text-xs text-slate-400 uppercase tracking-wide">Enterprise Write Safety Guard</p>
                </div>
              </div>

              <div className="text-sm text-slate-300 leading-relaxed bg-slate-900/40 p-4 rounded-xl border border-slate-800/80">
                {elicitation.message}
              </div>

              {elicitation.mode === "form" && elicitation.schema?.properties && (
                <div className="space-y-4">
                  {Object.entries(elicitation.schema.properties).map(([key, prop]: [string, any]) => {
                    const isRequired = elicitation.schema?.required?.includes(key);
                    return (
                      <div key={key} className="space-y-1.5">
                        <label className="text-xs font-semibold text-slate-400 flex justify-between">
                          <span>{prop.description ?? key}</span>
                          {isRequired && <span className="text-rose-500 text-[10px]">Required</span>}
                        </label>
                        {prop.type === "boolean" ? (
                          <div className="flex items-center space-x-3 bg-slate-900/20 p-3 rounded-lg border border-slate-800">
                            <input
                              type="checkbox"
                              checked={elicitFormData[key] || false}
                              onChange={(e) => setElicitFormData(prev => ({ ...prev, [key]: e.target.checked }))}
                              className="w-4 h-4 text-blue-600 bg-slate-900 border-slate-800 rounded focus:ring-blue-500"
                            />
                            <span className="text-xs text-slate-300">Enable / Approve</span>
                          </div>
                        ) : (
                          <input
                            type="text"
                            value={elicitFormData[key] || ""}
                            onChange={(e) => setElicitFormData(prev => ({ ...prev, [key]: e.target.value }))}
                            className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500"
                            placeholder={`Enter ${key}...`}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {elicitation.mode === "url" && elicitation.url && (
                <div className="space-y-3">
                  <p className="text-xs text-slate-400">Please visit the secure URL link to authenticate or grant safety consent:</p>
                  <a
                    href={elicitation.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center space-x-2 text-blue-400 hover:text-blue-300 underline text-xs font-semibold"
                  >
                    <LinkIcon className="w-4 h-4" />
                    <span>Open Elicitation URL Action</span>
                  </a>
                </div>
              )}

              <div className="flex space-x-3 pt-4 border-t border-slate-800 justify-end text-xs font-semibold">
                <button
                  onClick={() => handleElicitSubmit("decline")}
                  className="px-4 py-2.5 bg-rose-600/10 border border-rose-500/20 text-rose-400 hover:bg-rose-600/20 rounded-xl transition"
                >
                  Decline & Cancel
                </button>
                <button
                  onClick={() => handleElicitSubmit("accept")}
                  className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-slate-100 rounded-xl border border-blue-500/20 transition flex items-center space-x-1.5"
                >
                  <CheckCircle className="w-4 h-4" />
                  <span>Approve & Continue</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Subcomponent: Tool Call Card showing input arguments and outputs
function ToolCallCard({ tc }: { tc: ToolCall }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-3.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2 text-xs font-semibold text-slate-300">
          <Database className="w-3.5 h-3.5 text-blue-500" />
          <span>Tool: <code className="text-blue-400 font-mono text-[11px]">{tc.name}</code></span>
        </div>
        
        {/* Status indicator icon */}
        <div className="flex items-center space-x-2">
          {tc.result ? (
            <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20 font-medium">Success</span>
          ) : tc.error ? (
            <span className="text-[10px] text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-full border border-rose-500/20 font-medium flex items-center space-x-0.5">
              <AlertTriangle className="w-2.5 h-2.5" />
              <span>Failed</span>
            </span>
          ) : (
            <span className="text-[10px] text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full border border-blue-500/20 font-medium animate-pulse">Running</span>
          )}

          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1 hover:bg-slate-800 rounded text-slate-400"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="text-[11px] space-y-2 pt-2 border-t border-slate-800/60 font-mono">
          <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-850">
            <div className="font-semibold text-slate-500 mb-1">Arguments:</div>
            <pre className="text-slate-300 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(tc.arguments, null, 2)}</pre>
          </div>
          {tc.result && (
            <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-850">
              <div className="font-semibold text-slate-500 mb-1">Result:</div>
              <pre className="text-slate-300 overflow-x-auto whitespace-pre-wrap">{tc.result}</pre>
            </div>
          )}
          {tc.error && (
            <div className="bg-rose-950/20 p-2.5 rounded-lg border border-rose-500/15">
              <div className="font-semibold text-rose-400/80 mb-1">Error:</div>
              <pre className="text-rose-300 overflow-x-auto whitespace-pre-wrap">{tc.error}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
