import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
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
    __table_args__ = (UniqueConstraint("id", "run_id", name="uq_step_run_pipeline"),)
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
    __table_args__ = (
        CheckConstraint(
            "(actor_type = 'HUMAN' AND user_id IS NOT NULL AND actor_id = user_id) "
            "OR (actor_type IN ('AGENT', 'SERVICE') AND user_id IS NULL)",
            name="ck_audit_actor_identity",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(10), default="HUMAN")
    actor_id: Mapped[str] = mapped_column(String(100), index=True)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    parent_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", name="fk_audit_parent_event"), nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", name="fk_audit_project"), nullable=True, index=True
    )
    work_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("work_items.id", name="fk_audit_work_item"), nullable=True, index=True
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("execution_runs.id", name="fk_audit_execution_run"), nullable=True, index=True
    )
    result_id: Mapped[str | None] = mapped_column(
        ForeignKey("results.id", name="fk_audit_result"), nullable=True, index=True
    )
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


class WorkItemType(str, enum.Enum):
    EPIC = "EPIC"
    STORY = "STORY"
    TASK = "TASK"


class WorkItemStatus(str, enum.Enum):
    BACKLOG = "BACKLOG"
    READY = "READY"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    REVIEW = "REVIEW"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_FOR_CHILDREN = "WAITING_FOR_CHILDREN"
    NEEDS_INPUT = "NEEDS_INPUT"
    STALE = "STALE"


def domain_enum(values, name):
    # Portable CHECK-backed enums avoid PostgreSQL ALTER TYPE for future statuses.
    return Enum(values, name=name, native_enum=False, create_constraint=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(180))
    slug: Mapped[str] = mapped_column(String(180), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", name="fk_project_owner"))
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.private)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_work_item_project"),
        ForeignKeyConstraint(
            ["parent_id", "project_id"], ["work_items.id", "work_items.project_id"],
            name="fk_work_parent_project",
        ),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_work_not_own_parent"),
        CheckConstraint("type <> 'EPIC' OR parent_id IS NULL", name="ck_epic_root"),
        CheckConstraint("priority BETWEEN 0 AND 4", name="ck_work_priority"),
        CheckConstraint("version >= 1", name="ck_work_version"),
        CheckConstraint("owner_type IN ('HUMAN', 'AGENT')", name="ck_work_owner_type"),
        CheckConstraint(
            "(owner_type IS NULL AND owner_id IS NULL) OR "
            "(owner_type IS NOT NULL AND owner_id IS NOT NULL)", name="ck_work_owner_pair",
        ),
        CheckConstraint(
            "created_by_type IN ('HUMAN', 'AGENT', 'SERVICE')", name="ck_work_creator_type"
        ),
        Index("ix_work_project_status_priority", "project_id", "status", "priority"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", name="fk_work_project"))
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    type: Mapped[WorkItemType] = mapped_column(domain_enum(WorkItemType, "work_item_type"))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[WorkItemStatus] = mapped_column(
        domain_enum(WorkItemStatus, "work_item_status"), default=WorkItemStatus.BACKLOG
    )
    priority: Mapped[int] = mapped_column(Integer, default=2)
    owner_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by_type: Mapped[str] = mapped_column(String(10))
    created_by_id: Mapped[str] = mapped_column(String(100))
    created_from_run_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "execution_runs.id", name="fk_work_created_from_run", use_alter=True
        ), nullable=True
    )
    correlation_id: Mapped[str] = mapped_column(String(36), default=uuid4, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    parent: Mapped["WorkItem | None"] = relationship(
        remote_side=[id, project_id], back_populates="children"
    )
    children: Mapped[list["WorkItem"]] = relationship(back_populates="parent")
    runs: Mapped[list["ExecutionRun"]] = relationship(
        back_populates="task", foreign_keys="ExecutionRun.task_id"
    )
    __mapper_args__ = {"version_id_col": version}


class ExecutionRun(Base):
    """Agent invocation; optionally bridges a legacy pipeline step without another queue."""
    __tablename__ = "execution_runs"
    __table_args__ = (
        UniqueConstraint("id", "task_id", name="uq_execution_run_task"),
        CheckConstraint("parent_run_id IS NULL OR parent_run_id <> id", name="ck_run_not_own_parent"),
        ForeignKeyConstraint(
            ["step_run_id", "pipeline_run_id"], ["step_runs.id", "step_runs.run_id"],
            name="fk_execution_pipeline_step",
        ),
        CheckConstraint(
            "step_run_id IS NULL OR pipeline_run_id IS NOT NULL", name="ck_execution_step_pipeline"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("work_items.id", name="fk_execution_task"), index=True
    )
    pipeline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_runs.id", name="fk_execution_pipeline"), nullable=True, index=True
    )
    step_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    pipeline_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("pipeline_versions.id", name="fk_execution_pipeline_version"), nullable=True
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", name="fk_execution_agent"))
    agent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_versions.id", name="fk_execution_agent_version"), nullable=True
    )
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(240), nullable=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.queued)
    parent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("execution_runs.id", name="fk_execution_parent"), nullable=True, index=True
    )
    correlation_id: Mapped[str] = mapped_column(String(36), default=uuid4, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    task: Mapped[WorkItem] = relationship(back_populates="runs", foreign_keys=[task_id])
    parent: Mapped["ExecutionRun | None"] = relationship(remote_side=[id])
    results: Mapped[list["Result"]] = relationship(back_populates="run")


class Result(Base):
    __tablename__ = "results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "task_id"], ["execution_runs.id", "execution_runs.task_id"],
            name="fk_result_run_task",
        ),
        CheckConstraint(
            "validation_status IN ('PENDING', 'VALID', 'INVALID')", name="ck_result_validation"
        ),
        CheckConstraint(
            "review_status IN ('NOT_REQUESTED', 'PENDING', 'APPROVED', 'REJECTED')",
            name="ck_result_review",
        ),
        CheckConstraint(
            "freshness_status IN ('CURRENT', 'STALE', 'UNKNOWN')", name="ck_result_freshness"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("work_items.id", name="fk_result_task"), index=True
    )
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    result_type: Mapped[str] = mapped_column(String(80))
    structured_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    artifact_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    validation_status: Mapped[str] = mapped_column(String(12), default="PENDING")
    review_status: Mapped[str] = mapped_column(String(16), default="NOT_REQUESTED")
    freshness_status: Mapped[str] = mapped_column(String(10), default="UNKNOWN")
    freshness_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    run: Mapped[ExecutionRun] = relationship(back_populates="results")
