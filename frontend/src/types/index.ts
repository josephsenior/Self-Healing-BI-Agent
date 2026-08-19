export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  status?: "running" | "complete" | "failed" | "cancelled";
  result?: string;
  error?: string;
  images?: string[];
}

export type MessagePart =
  | { type: "reasoning"; text: string }
  | { type: "text"; text: string }
  | { type: "tool_call"; toolCall: ToolCall };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  reasoningContent?: string;
  toolCalls?: ToolCall[];
  parts?: MessagePart[];
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

export interface DashboardVersion {
  version: number;
  spec: DashboardSpec;
  reason: string;
  created_at: string;
}

export interface DashboardSpec {
  title: string;
  dataset: { path: string };
  pages: DashboardPage[];
}

export interface DashboardPage {
  name: string;
  visuals: VisualSpec[];
}

export interface VisualSpec {
  type: string;
  title: string;
  position: { column: number; row: number; width: number; height: number };
  fields?: Record<string, FieldRef[]>;
  category?: FieldRef[];
  values?: FieldRef[];
  series?: FieldRef;
  font_color?: string;
  font_size?: number;
  text_alignment?: string;
  content?: string;
  shape_type?: string;
  image_url?: string;
  action?: { type: string; target: string };
}

export interface FieldRef {
  table: string;
  name: string;
  kind?: string;
}

export interface DashboardState {
  title: string;
  version: number;
  published: boolean;
  rendered: boolean;
  dashboard_id: string;
}

export interface CloudReadiness {
  ready: boolean;
  publishing_ready: boolean;
  visual_qa_ready: boolean;
  license_mode: string;
  rendering_supported: boolean;
  limitations: string[];
  checks: Record<string, boolean>;
}

export interface VisualCapability {
  visual_type: string;
  family: string;
  min_total_fields: number;
  roles: Record<string, FieldRole>;
  configuration: string[];
}

export interface FieldRole {
  query_role: string;
  min_fields: number;
  max_fields: number;
  field_kind: string;
}

export interface SemanticModel {
  id: string;
  name: string;
  description?: string;
}

export interface QualificationResult {
  success: boolean;
  semantic_model_id?: string;
  report_id?: string;
  workspace_id?: string;
  error?: string;
}

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export type AgentStatus = "idle" | "starting_agent" | "mcp_connected" | "running" | "complete" | "cancelled" | "error";

export type WSOutgoingMessage =
  | { type: "query"; text: string; reasoningEffort?: string; threadId: string }
  | { type: "elicitation_response"; id: string; action: "accept" | "decline" | "cancel"; content: Record<string, unknown> }
  | { type: "abort" };

export type WSIncomingMessage =
  | { type: "status"; status: string }
  | { type: "token"; text: string }
  | { type: "reasoning_token"; text: string }
  | { type: "tool_start"; calls: { id: string; name: string; arguments: Record<string, unknown> }[] }
  | { type: "tool_result"; id: string; name: string; result?: string; error?: string; images?: string[] }
  | { type: "tools_discovered"; tools: string[]; count: number }
  | { type: "thread_ready"; threadId: string }
  | { type: "elicitation_request"; id: string; mode: "form" | "url"; message: string; schema?: Record<string, unknown>; url?: string }
  | { type: "complete" }
  | { type: "error"; message: string };
