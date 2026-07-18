from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import AgentKind, RunStatus, TriggerKind, Visibility, WorkerStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: str
    email: str
    display_name: str
    is_root: bool


class UserAdminOut(UserOut):
    is_active: bool
    created_at: datetime


class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = ""


class GroupOut(ORMModel):
    id: str
    name: str
    description: str
    manager_id: str


class ProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: Literal["ollama", "openai-compatible"]
    base_url: str = Field(min_length=7, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    enabled: bool = True


class ProviderOut(ORMModel):
    id: str
    name: str
    kind: str
    base_url: str
    enabled: bool
    model_count: int = 0
    has_api_key: bool = False


class ModelOut(ORMModel):
    id: str
    provider_id: str
    model_id: str
    display_name: str
    capabilities: dict[str, Any]
    enabled: bool


class ProviderConnectionResult(BaseModel):
    ok: bool
    message: str
    models: list[str] = Field(default_factory=list)


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str = ""
    purpose: str = ""
    kind: AgentKind = AgentKind.ai
    execution_requirement: Literal["cpu", "gpu"] = "cpu"
    visibility: Visibility = Visibility.private
    provider_id: str | None = None
    model_catalog_id: str | None = None
    mcp_server_id: str | None = None
    mcp_tool_name: str | None = Field(default=None, min_length=1, max_length=128)
    draft_config: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class AgentOut(AgentCreate, ORMModel):
    id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime


class McpServerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str = ""
    transport: Literal["streamable-http", "stdio"] = "streamable-http"
    endpoint: str | None = Field(default=None, max_length=1000)
    command: list[str] = Field(default_factory=list, max_length=100)
    visibility: Visibility = Visibility.private
    secret_headers: dict[str, str] = Field(default_factory=dict)
    secret_environment: dict[str, str] = Field(default_factory=dict)


class McpServerOut(ORMModel):
    id: str
    name: str
    slug: str
    description: str
    transport: str
    endpoint: str | None
    command: list[str]
    visibility: Visibility
    owner_id: str
    status: Literal["unknown", "online", "error", "disabled"]
    status_message: str
    protocol_version: str | None
    server_info: dict[str, Any]
    capabilities: dict[str, Any]
    tools_snapshot: list[dict[str, Any]]
    has_secret: bool = False
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class McpConnectionResult(BaseModel):
    ok: bool
    message: str
    protocol_version: str | None = None
    server_info: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    tools: list[dict[str, Any]] = Field(default_factory=list)


class PipelineCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str = ""
    visibility: Visibility = Visibility.private
    graph: dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})
    input_schema: dict[str, Any] = Field(default_factory=dict)
    engine: Literal["legacy", "langgraph"] = "langgraph"


class PipelineOut(PipelineCreate, ORMModel):
    id: str
    owner_id: str
    created_at: datetime
    updated_at: datetime


class PipelineValidationOut(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TriggerCreate(BaseModel):
    kind: TriggerKind
    name: str = Field(min_length=2, max_length=140)
    enabled: bool = True
    configuration: dict[str, Any] = Field(default_factory=dict)


class TriggerOut(TriggerCreate, ORMModel):
    id: str
    pipeline_id: str
    last_fired_at: datetime | None
    next_fire_at: datetime | None


class RunCreate(BaseModel):
    trigger_kind: TriggerKind = TriggerKind.manual
    trigger_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)


class StepOut(ORMModel):
    id: str
    node_id: str
    position: int
    title: str
    agent_name: str
    status: RunStatus
    progress: int
    current_action: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None


class RunOut(ORMModel):
    id: str
    sequence: int
    pipeline_id: str
    pipeline_name: str
    trigger_kind: TriggerKind
    engine: Literal["legacy", "langgraph"]
    status: RunStatus
    input_payload: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    steps: list[StepOut] = Field(default_factory=list)


class RunPageOut(BaseModel):
    items: list[RunOut] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    pages: int


class RunFilterOptions(BaseModel):
    pipelines: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)


class EventCreate(BaseModel):
    step_run_id: str | None = None
    kind: str
    level: Literal["debug", "info", "warning", "error"] = "info"
    title: str
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class EventOut(EventCreate, ORMModel):
    id: str
    run_id: str
    created_at: datetime


class AuditEventCreate(BaseModel):
    kind: str = Field(max_length=80)
    level: Literal["info", "success", "warning", "error"] = "info"
    message: str = Field(max_length=500)
    resource_type: str | None = Field(default=None, max_length=40)
    resource_id: str | None = Field(default=None, max_length=36)
    payload: dict[str, Any] = Field(default_factory=dict)


class AuditEventOut(AuditEventCreate, ORMModel):
    id: str
    user_id: str
    created_at: datetime


class WorkerRegistrationTokenCreate(BaseModel):
    name_hint: str = Field(default="", max_length=160)
    expires_in_minutes: int = Field(default=30, ge=5, le=1440)


class WorkerRegistrationTokenOut(BaseModel):
    token: str
    expires_at: datetime


class WorkerRegister(BaseModel):
    registration_token: str = Field(min_length=20)
    name: str = Field(min_length=2, max_length=160)
    worker_class: Literal["cpu", "gpu", "universal"] = "universal"
    executors: list[Literal["process", "podman", "builtin", "managed-ai", "mcp", "crewai"]] = Field(
        default_factory=lambda: ["process", "builtin"]
    )
    labels: dict[str, str] = Field(default_factory=dict)
    version: str = Field(default="unknown", max_length=40)
    platform: str = Field(default="linux", max_length=80)
    architecture: str = Field(default="unknown", max_length=40)


class WorkerCredentials(BaseModel):
    worker_id: str
    worker_token: str


class WorkerOut(ORMModel):
    id: str
    name: str
    status: WorkerStatus
    worker_class: Literal["cpu", "gpu", "universal"]
    executors: list[str]
    labels: dict[str, str]
    version: str
    platform: str
    architecture: str
    last_seen_at: datetime
    registered_at: datetime


class WorkerHeartbeat(BaseModel):
    executors: list[str] = Field(default_factory=list)
    version: str = Field(default="unknown", max_length=40)


class WorkerJobOut(BaseModel):
    id: str
    lease_token: str
    executor: str
    required_worker_class: Literal["cpu", "gpu"]
    run_id: str
    step_run_id: str
    input_payload: dict[str, Any]
    config: dict[str, Any]


class WorkerJobEvent(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str = Field(max_length=10000)


class WorkerJobComplete(BaseModel):
    lease_token: str
    success: bool
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error: str = Field(default="", max_length=20000)
