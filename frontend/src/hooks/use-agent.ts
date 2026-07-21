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
  const activeToolCallsRef = useRef<ToolCall[]>([]);

  // Keep ref in sync with state for use inside closures
  useEffect(() => {
    activeToolCallsRef.current = activeToolCalls;
  }, [activeToolCalls]);

  const handleMessage = useCallback((event: MessageEvent) => {
    const payload: WSIncomingMessage = JSON.parse(event.data);

    switch (payload.type) {
      case "status":
        setAgentStatus(payload.status as AgentStatus);
        if (payload.status === "starting_agent") {
          setActiveToolCalls([]);
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
        setActiveToolCalls((prev) =>
          prev.map((c) =>
            c.id === payload.id
              ? { ...c, result: payload.result, error: payload.error }
              : c
          )
        );

        setMessages((prev) => {
          if (prev.length === 0 || prev[prev.length - 1].role !== "assistant") return prev;

          const updated = [...prev];
          const last = { ...updated[updated.length - 1] };

          if (last.toolCalls) {
            last.toolCalls = last.toolCalls.map((c) =>
              c.id === payload.id ? { ...c, result: payload.result, error: payload.error } : c
            );
          }

          if (last.parts) {
            last.parts = last.parts.map((p) => {
              if (p.type === "tool_call" && p.toolCall.id === payload.id) {
                return {
                  ...p,
                  toolCall: {
                    ...p.toolCall,
                    result: payload.result,
                    error: payload.error,
                  },
                };
              }
              return p;
            });
          }

          updated[updated.length - 1] = last;
          return updated;
        });
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
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      return;
    }

    if (socketRef.current) {
      socketRef.current.close();
    }

    setConnectionStatus("connecting");
    const ws = new WebSocket(url);
    socketRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus("connected");
      setAgentStatus((prev) => (prev === "error" ? "idle" : prev));
    };

    ws.onclose = () => {
      setConnectionStatus("disconnected");
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
    connect();

    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (socketRef.current) {
        socketRef.current.close();
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

    // Send over WebSocket
    const msg: WSOutgoingMessage = { type: "query", text, reasoningEffort };
    socketRef.current.send(JSON.stringify(msg));

    setAgentStatus("running");
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
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
    }
    if (socketRef.current) {
      socketRef.current.close();
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
  };
}
