export type Visibility = 'private' | 'public' | 'groups'
export type AgentKind = 'ai' | 'script' | 'mcp' | 'crewai'
export type TriggerKind = 'manual' | 'cron' | 'api'
export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface User {
  id: string
  email: string
  display_name: string
  is_root: boolean
}

export interface Agent {
  id: string
  name: string
  slug: string
  description: string
  purpose: string
  kind: AgentKind
  execution_requirement: 'cpu' | 'gpu'
  visibility: Visibility
  owner_id: string
  provider_id?: string
  model_catalog_id?: string
  mcp_server_id?: string
  mcp_tool_name?: string
  draft_config: Record<string, unknown>
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface Pipeline {
  id: string
  name: string
  slug: string
  description: string
  visibility: Visibility
  owner_id: string
  graph: { nodes: unknown[]; edges: unknown[] }
  input_schema: Record<string, unknown>
  engine: 'legacy' | 'langgraph'
  created_at: string
  updated_at: string
}

export interface StepRun {
  id: string
  node_id: string
  position: number
  title: string
  agent_name: string
  status: RunStatus
  progress: number
  current_action: string
  input_payload: Record<string, unknown>
  output_payload: Record<string, unknown>
  started_at?: string
  finished_at?: string
}

export interface PipelineRun {
  id: string
  sequence: number
  pipeline_id: string
  pipeline_name: string
  trigger_kind: TriggerKind
  engine: 'legacy' | 'langgraph'
  status: RunStatus
  input_payload: Record<string, unknown>
  created_at: string
  started_at?: string
  finished_at?: string
  steps: StepRun[]
}

export interface RunEvent {
  id: string
  run_id: string
  step_run_id?: string
  kind: string
  level: 'debug' | 'info' | 'warning' | 'error'
  title: string
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export interface Provider {
  id: string
  name: string
  kind: 'ollama' | 'openai-compatible'
  base_url: string
  enabled: boolean
  model_count: number
  has_api_key: boolean
}

export interface ProviderModel {
  id: string
  provider_id: string
  model_id: string
  display_name: string
  capabilities: Record<string, unknown>
  enabled: boolean
}

export interface Group {
  id: string
  name: string
  description: string
  manager_id: string
}

export interface AdminUser extends User {
  is_active: boolean
  created_at: string
}

export interface Worker {
  id: string
  name: string
  status: 'online' | 'offline' | 'disabled'
  worker_class: 'cpu' | 'gpu' | 'universal'
  executors: string[]
  labels: Record<string, string>
  version: string
  platform: string
  architecture: string
  last_seen_at: string
  registered_at: string
}

export interface McpTool {
  name: string
  title?: string
  description?: string
  inputSchema: Record<string, unknown>
  outputSchema?: Record<string, unknown>
  annotations?: Record<string, unknown>
}

export interface McpServer {
  id: string
  name: string
  slug: string
  description: string
  transport: 'streamable-http' | 'stdio'
  endpoint?: string
  command: string[]
  visibility: Visibility
  owner_id: string
  status: 'unknown' | 'online' | 'error' | 'disabled'
  status_message: string
  protocol_version?: string
  server_info: Record<string, unknown>
  capabilities: Record<string, unknown>
  tools_snapshot: McpTool[]
  has_secret: boolean
  last_checked_at?: string
  created_at: string
  updated_at: string
}
