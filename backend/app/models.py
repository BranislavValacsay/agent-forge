import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uuid4() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Visibility(str, enum.Enum):
    private = "private"
    public = "public"
    groups = "groups"


class AgentKind(str, enum.Enum):
    ai = "ai"
    script = "script"
    mcp = "mcp"
    crewai = "crewai"


class TriggerKind(str, enum.Enum):
    manual = "manual"
    cron = "cron"
    api = "api"


class RunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class WorkerStatus(str, enum.Enum):
    online = "online"
    offline = "offline"
    disabled = "disabled"


class JobStatus(str, enum.Enum):
    queued = "queued"
    leased = "leased"
    succeeded = "succeeded"
    failed = "failed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(500))
    is_root: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    locale: Mapped[str] = mapped_column(String(10), default="sk")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Group(Base):
    __tablename__ = "groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    manager_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(60), default="openai-compatible")
    base_url: Mapped[str] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class ModelCatalog(Base):
    __tablename__ = "model_catalog"
    __table_args__ = (UniqueConstraint("provider_id", "model_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    model_id: Mapped[str] = mapped_column(String(240))
    display_name: Mapped[str] = mapped_column(String(240))
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ProviderSecret(Base):
    __tablename__ = "provider_secrets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), unique=True
    )
    encrypted_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class McpServer(Base):
    __tablename__ = "mcp_servers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), index=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    transport: Mapped[str] = mapped_column(String(30), default="streamable-http")
    endpoint: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    command: Mapped[list[str]] = mapped_column(JSON, default=list)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.private)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    status_message: Mapped[str] = mapped_column(Text, default="Not checked")
    protocol_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    server_info: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tools_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class McpServerSecret(Base):
    __tablename__ = "mcp_server_secrets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    mcp_server_id: Mapped[str] = mapped_column(
        ForeignKey("mcp_servers.id", ondelete="CASCADE"), unique=True
    )
    encrypted_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), index=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[AgentKind] = mapped_column(Enum(AgentKind))
    execution_requirement: Mapped[str] = mapped_column(String(20), default="cpu", index=True)
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.private)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider_id: Mapped[str | None] = mapped_column(ForeignKey("providers.id"), nullable=True)
    model_catalog_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_catalog.id"), nullable=True
    )
    mcp_server_id: Mapped[str | None] = mapped_column(
        ForeignKey("mcp_servers.id"), nullable=True, index=True
    )
    mcp_tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    draft_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AclEntry(Base):
    __tablename__ = "acl_entries"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", "subject_type", "subject_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    resource_type: Mapped[str] = mapped_column(String(40), index=True)
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[str] = mapped_column(String(36))
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)


class Pipeline(Base):
    __tablename__ = "pipelines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(180), index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.private)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, default=lambda: {"nodes": [], "edges": []})
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    engine: Mapped[str] = mapped_column(String(30), default="langgraph", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class PipelineVersion(Base):
    __tablename__ = "pipeline_versions"
    __table_args__ = (UniqueConstraint("pipeline_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PipelineTrigger(Base):
    __tablename__ = "pipeline_triggers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"))
    kind: Mapped[TriggerKind] = mapped_column(Enum(TriggerKind))
    name: Mapped[str] = mapped_column(String(140))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_fire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    sequence: Mapped[int] = mapped_column(Integer, index=True)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id"), index=True)
    pipeline_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_versions.id"), nullable=True
    )
    trigger_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_triggers.id"), nullable=True
    )
    trigger_kind: Mapped[TriggerKind] = mapped_column(Enum(TriggerKind))
    triggered_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.queued)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    graph_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    engine: Mapped[str] = mapped_column(String(30), default="langgraph", index=True)
    locale: Mapped[str] = mapped_column(String(10), default="sk")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    pipeline: Mapped["Pipeline"] = relationship()
    steps: Mapped[list["StepRun"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="StepRun.position"
    )

    @property
    def pipeline_name(self) -> str:
        name = self.pipeline.name
        return f"{name.split(':', 2)[-1]} (deleted)" if name.startswith("__deleted__:") else name


class StepRun(Base):
    __tablename__ = "step_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(180))
    agent_name: Mapped[str] = mapped_column(String(180))
    agent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_versions.id"), nullable=True
    )
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.queued)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_action: Mapped[str] = mapped_column(String(300), default="Čaká na spustenie")
    current_action_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    current_action_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run: Mapped[PipelineRun] = relationship(back_populates="steps")
    events: Mapped[list["RunEvent"]] = relationship(cascade="all, delete-orphan")


class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    step_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("step_runs.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(80), index=True)
    level: Mapped[str] = mapped_column(String(20), default="info")
    title: Mapped[str] = mapped_column(String(240))
    title_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    title_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text, default="")
    message_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    message_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    level: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text)
    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class WorkerRegistrationToken(Base):
    __tablename__ = "worker_registration_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name_hint: Mapped[str] = mapped_column(String(160), default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), index=True)
    credential_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[WorkerStatus] = mapped_column(Enum(WorkerStatus), default=WorkerStatus.online)
    worker_class: Mapped[str] = mapped_column(String(20), default="universal", index=True)
    executors: Mapped[list[str]] = mapped_column(JSON, default=list)
    labels: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    version: Mapped[str] = mapped_column(String(40), default="unknown")
    platform: Mapped[str] = mapped_column(String(80), default="linux")
    architecture: Mapped[str] = mapped_column(String(40), default="unknown")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkerJob(Base):
    __tablename__ = "worker_jobs"
    __table_args__ = (UniqueConstraint("step_run_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    step_run_id: Mapped[str] = mapped_column(
        ForeignKey("step_runs.id", ondelete="CASCADE"), index=True
    )
    executor: Mapped[str] = mapped_column(String(40), index=True)
    required_worker_class: Mapped[str] = mapped_column(String(20), default="cpu", index=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, index=True)
    worker_id: Mapped[str | None] = mapped_column(
        ForeignKey("workers.id"), nullable=True, index=True
    )
    lease_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
