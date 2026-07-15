export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string;
  error?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  reasoningContent?: string;
  toolCalls?: ToolCall[];
  timestamp: Date;
}

export interface ElicitationRequest {
  id: string;
  mode: "form" | "url";
  message: string;
  schema?: {
    properties?: Record<string, {
      type?: string;
      description?: string;
      default?: unknown;
      [key: string]: unknown;
    }>;
    required?: string[];
    [key: string]: unknown;
  };
  url?: string;
}

export interface AgentConfig {
  llm_provider: string;
  llm_model: string;
  transport_mode: string;
  sse_url?: string | null;
}

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export type AgentStatus = "idle" | "starting_agent" | "mcp_connected" | "running" | "complete" | "cancelled" | "error";

export type WSOutgoingMessage =
  | { type: "query"; text: string; reasoningEffort?: string }
  | { type: "elicitation_response"; id: string; action: "accept" | "decline" | "cancel"; content: Record<string, unknown> }
  | { type: "abort" };

export type WSIncomingMessage =
  | { type: "status"; status: string }
  | { type: "token"; text: string }
  | { type: "reasoning_token"; text: string }
  | { type: "tool_start"; calls: { id: string; name: string; arguments: Record<string, unknown> }[] }
  | { type: "tool_result"; id: string; name: string; result?: string; error?: string }
  | { type: "tools_discovered"; tools: string[]; count: number }
  | { type: "elicitation_request"; id: string; mode: "form" | "url"; message: string; schema?: Record<string, unknown>; url?: string }
  | { type: "complete" }
  | { type: "error"; message: string };
