"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  ChatMessage,
  ToolCall,
  ElicitationRequest,
  ConnectionStatus,
  AgentStatus,
  WSIncomingMessage,
  WSOutgoingMessage,
} from "@/types";

interface UseAgentReturn {
  connectionStatus: ConnectionStatus;
  agentStatus: AgentStatus;
  messages: ChatMessage[];
  activeToolCalls: ToolCall[];
  elicitation: ElicitationRequest | null;
  discoveredTools: string[];
  sendQuery: (text: string, reasoningEffort?: string) => void;
  respondToElicitation: (
    id: string,
    action: "accept" | "decline" | "cancel",
    content: Record<string, unknown>
  ) => void;
  abort: () => void;
  reconnect: () => void;
  loadConversation: (threadId: string, messages: ChatMessage[]) => void;
  clearConversation: () => void;
}

function interruptRunningToolCalls(messages: ChatMessage[], reason: string): ChatMessage[] {
  const settle = (toolCall: ToolCall): ToolCall => {
    const pending =
      toolCall.status === "running" ||
      (toolCall.status === undefined && toolCall.result === undefined && !toolCall.error);
    return pending ? { ...toolCall, status: "cancelled", error: reason } : toolCall;
  };

  return messages.map((message) => ({
    ...message,
    toolCalls: message.toolCalls?.map(settle),
    parts: message.parts?.map((part) =>
      part.type === "tool_call" ? { ...part, toolCall: settle(part.toolCall) } : part
    ),
  }));
}

export function useAgent(url: string): UseAgentReturn {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("disconnected");
  const [agentStatus, setAgentStatus] = useState<AgentStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeToolCalls, setActiveToolCalls] = useState<ToolCall[]>([]);
  const [elicitation, setElicitation] = useState<ElicitationRequest | null>(null);
  const [discoveredTools, setDiscoveredTools] = useState<string[]>([]);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(true);
  const activeToolCallsRef = useRef<ToolCall[]>([]);
  const threadIdRef = useRef<string | null>(null);

  // Keep ref in sync with state for use inside closures
  useEffect(() => {
    activeToolCallsRef.current = activeToolCalls;
  }, [activeToolCalls]);

  const handleMessage = useCallback((event: MessageEvent) => {
    const payload: WSIncomingMessage = JSON.parse(event.data);

    switch (payload.type) {
      case "status":
        setAgentStatus(payload.status as AgentStatus);
        if (["starting_agent", "idle", "cancelled", "error"].includes(payload.status)) {
          setActiveToolCalls([]);
          setMessages((prev) => interruptRunningToolCalls(prev, "Execution was interrupted."));
        }
        break;

      case "token":
        setMessages((prev) => {
          const updated = [...prev];
          let last: ChatMessage;

          if (updated.length === 0 || updated[updated.length - 1].role !== "assistant") {
            last = {
              id: crypto.randomUUID(),
              role: "assistant",
              content: payload.text,
              reasoningContent: "",
              toolCalls: [],
              parts: [{ type: "text", text: payload.text }],
              timestamp: new Date(),
            };
            return [...updated, last];
          }

          last = { ...updated[updated.length - 1] };
          last.content = (last.content || "") + payload.text;

          const parts = [...(last.parts || [])];
          const lastPart = parts.length > 0 ? parts[parts.length - 1] : null;

          if (lastPart && lastPart.type === "text") {
            parts[parts.length - 1] = {
              ...lastPart,
              text: lastPart.text + payload.text,
            };
          } else {
            parts.push({ type: "text", text: payload.text });
          }

          last.parts = parts;
          updated[updated.length - 1] = last;
          return updated;
        });
        break;

      case "reasoning_token":
        setMessages((prev) => {
          const updated = [...prev];
          let last: ChatMessage;

          if (updated.length === 0 || updated[updated.length - 1].role !== "assistant") {
            last = {
              id: crypto.randomUUID(),
              role: "assistant",
              content: "",
              reasoningContent: payload.text,
              toolCalls: [],
              parts: [{ type: "reasoning", text: payload.text }],
              timestamp: new Date(),
            };
            return [...updated, last];
          }

          last = { ...updated[updated.length - 1] };
          last.reasoningContent = (last.reasoningContent || "") + payload.text;

          const parts = [...(last.parts || [])];
          const lastPart = parts.length > 0 ? parts[parts.length - 1] : null;

          if (lastPart && lastPart.type === "reasoning") {
            parts[parts.length - 1] = {
              ...lastPart,
              text: lastPart.text + payload.text,
            };
          } else {
            parts.push({ type: "reasoning", text: payload.text });
          }

          last.parts = parts;
          updated[updated.length - 1] = last;
          return updated;
        });
        break;

      case "tool_start": {
        const started: ToolCall[] = payload.calls.map((c) => ({
          id: c.id,
          name: c.name,
          arguments: c.arguments,
          status: "running",
        }));
        setActiveToolCalls((prev) => [...prev, ...started]);

        setMessages((prev) => {
          const updated = [...prev];
          let last: ChatMessage;

          if (updated.length === 0 || updated[updated.length - 1].role !== "assistant") {
            last = {
              id: crypto.randomUUID(),
              role: "assistant",
              content: "",
              reasoningContent: "",
              toolCalls: [...started],
              parts: started.map((tc) => ({ type: "tool_call", toolCall: tc })),
              timestamp: new Date(),
            };
            return [...updated, last];
          }

          last = { ...updated[updated.length - 1] };
          last.toolCalls = [...(last.toolCalls || []), ...started];

          const parts = [...(last.parts || [])];
          for (const tc of started) {
            const exists = parts.some((p) => p.type === "tool_call" && p.toolCall.id === tc.id);
            if (!exists) {
              parts.push({ type: "tool_call", toolCall: tc });
            }
          }

          last.parts = parts;
          updated[updated.length - 1] = last;
          return updated;
        });
        break;
      }

      case "tool_result":
        // A result means this call is no longer active. Keeping it here made
        // completed calls render as "Running".
        setActiveToolCalls((prev) => prev.filter((c) => c.id !== payload.id));

        const completionStatus: ToolCall["status"] = payload.error ? "failed" : "complete";
        setMessages((prev) => prev.map((message) => {
          // Results can arrive after another assistant event, so search all messages.
          let changed = false;
          const toolCalls = message.toolCalls?.map((call) => {
            if (call.id !== payload.id) return call;
            changed = true;
            return { ...call, status: completionStatus, result: payload.result ?? "", error: payload.error };
          });
          const parts = message.parts?.map((part) => {
            if (part.type !== "tool_call" || part.toolCall.id !== payload.id) return part;
            changed = true;
            return { ...part, toolCall: { ...part.toolCall, status: completionStatus, result: payload.result ?? "", error: payload.error } };
          });
          return changed ? { ...message, toolCalls, parts } : message;
        }));
        break;

      case "thread_ready":
        if (!threadIdRef.current) threadIdRef.current = payload.threadId;
        break;
      case "tools_discovered":
        setDiscoveredTools(payload.tools);
        break;

      case "elicitation_request":
        setElicitation({
          id: payload.id,
          mode: payload.mode,
          message: payload.message,
          schema: payload.schema as ElicitationRequest["schema"],
          url: payload.url,
        });
        break;

      case "complete":
        setActiveToolCalls([]);
        setAgentStatus("idle");
        break;

      case "error":
        setActiveToolCalls([]);
        setAgentStatus("error");
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `System Error: ${payload.message}`,
            timestamp: new Date(),
          },
        ]);
        break;
    }
  }, []);

  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (
      socketRef.current &&
      (socketRef.current.readyState === WebSocket.OPEN ||
        socketRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    if (socketRef.current) {
      socketRef.current.onclose = null;
      socketRef.current.close();
      socketRef.current = null;
    }

    setConnectionStatus("connecting");
    const ws = new WebSocket(url);
    socketRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus("connected");
      setAgentStatus((prev) => (prev === "error" ? "idle" : prev));
    };

    ws.onclose = () => {
      if (socketRef.current === ws) socketRef.current = null;
      setConnectionStatus("disconnected");
      setActiveToolCalls([]);
      setMessages((prev) => interruptRunningToolCalls(prev, "Connection closed before the tool returned."));
      if (!shouldReconnectRef.current) return;
      // Auto-reconnect after 3 seconds
      reconnectTimer.current = setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = () => {
      setConnectionStatus("error");
    };

    ws.onmessage = handleMessage;
  }, [url, handleMessage]);

  // Connect on mount, cleanup on unmount
  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();

    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [connect]);

  const sendQuery = useCallback((text: string, reasoningEffort?: string) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;

    // Add user message
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: new Date(),
      },
    ]);

    // Clear any residual state
    setActiveToolCalls([]);

    // Send over WebSocket using the selected persisted conversation.
    let threadId = threadIdRef.current;
    if (!threadId) {
      threadId = crypto.randomUUID();
      threadIdRef.current = threadId;
    }
    const msg: WSOutgoingMessage = { type: "query", text, reasoningEffort, threadId };
    socketRef.current.send(JSON.stringify(msg));

    setAgentStatus("running");
  }, []);

  const loadConversation = useCallback((threadId: string, nextMessages: ChatMessage[]) => {
    threadIdRef.current = threadId;
    setMessages(nextMessages);
    setActiveToolCalls([]);
    setElicitation(null);
    setAgentStatus("idle");
  }, []);

  const clearConversation = useCallback(() => {
    threadIdRef.current = crypto.randomUUID();
    setMessages([]);
    setActiveToolCalls([]);
    setElicitation(null);
    setAgentStatus("idle");
  }, []);

  const respondToElicitation = useCallback(
    (id: string, action: "accept" | "decline" | "cancel", content: Record<string, unknown>) => {
      if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;

      const msg: WSOutgoingMessage = {
        type: "elicitation_response",
        id,
        action,
        content,
      };
      socketRef.current.send(JSON.stringify(msg));
      setElicitation(null);
    },
    []
  );

  const abort = useCallback(() => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
    const msg: WSOutgoingMessage = { type: "abort" };
    socketRef.current.send(JSON.stringify(msg));
  }, []);

  const reconnect = useCallback(() => {
    shouldReconnectRef.current = true;
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (socketRef.current) {
      socketRef.current.onclose = null;
      socketRef.current.close();
      socketRef.current = null;
    }
    connect();
  }, [connect]);

  return {
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
  };
}
