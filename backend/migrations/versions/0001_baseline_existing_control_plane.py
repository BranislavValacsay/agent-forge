"""baseline existing control plane

Revision ID: 0001
Revises:
Create Date: 2026-10-03 11:12:54.888721

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def legacy_enum(*values, name):
    return sa.Enum(*values, name=name).with_variant(
        postgresql.ENUM(*values, name=name, create_type=False), "postgresql"
    )


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_schema() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == "postgresql":
        for name, values in {
            "workerstatus": ["online", "offline", "disabled"],
            "visibility": ["private", "public", "groups"],
            "triggerkind": ["manual", "cron", "api"],
            "agentkind": ["ai", "script", "mcp", "crewai"],
            "runstatus": ["queued", "running", "succeeded", "failed", "cancelled"],
            "jobstatus": ["queued", "leased", "succeeded", "failed"],
        }.items():
            postgresql.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)
    op.create_table(
        "acl_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("subject_type", sa.String(length=20), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource_type", "resource_id", "subject_type", "subject_id"),
    )
    with op.batch_alter_table("acl_entries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_acl_entries_resource_id"), ["resource_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_acl_entries_resource_type"), ["resource_type"], unique=False
        )

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("is_root", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)

    op.create_table(
        "workers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            legacy_enum("online", "offline", "disabled", name="workerstatus"),
            nullable=False,
        ),
        sa.Column("worker_class", sa.String(length=20), nullable=False),
        sa.Column("executors", sa.JSON(), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("architecture", sa.String(length=40), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("workers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_workers_credential_hash"), ["credential_hash"], unique=True
        )
        batch_op.create_index(batch_op.f("ix_workers_last_seen_at"), ["last_seen_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_workers_name"), ["name"], unique=False)
        batch_op.create_index(batch_op.f("ix_workers_worker_class"), ["worker_class"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_audit_events_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_audit_events_kind"), ["kind"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_events_resource_id"), ["resource_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_audit_events_resource_type"), ["resource_type"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_audit_events_user_id"), ["user_id"], unique=False)

    op.create_table(
        "groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("manager_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("transport", sa.String(length=30), nullable=False),
        sa.Column("endpoint", sa.String(length=1000), nullable=True),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column(
            "visibility",
            legacy_enum("private", "public", "groups", name="visibility"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("status_message", sa.Text(), nullable=False),
        sa.Column("protocol_version", sa.String(length=30), nullable=True),
        sa.Column("server_info", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("tools_snapshot", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("mcp_servers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mcp_servers_name"), ["name"], unique=False)
        batch_op.create_index(batch_op.f("ix_mcp_servers_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_mcp_servers_slug"), ["slug"], unique=True)
        batch_op.create_index(batch_op.f("ix_mcp_servers_status"), ["status"], unique=False)

    op.create_table(
        "pipelines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "visibility",
            legacy_enum("private", "public", "groups", name="visibility"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("engine", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pipelines", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pipelines_engine"), ["engine"], unique=False)
        batch_op.create_index(batch_op.f("ix_pipelines_name"), ["name"], unique=False)
        batch_op.create_index(batch_op.f("ix_pipelines_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pipelines_slug"), ["slug"], unique=True)

    op.create_table(
        "providers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "worker_registration_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("name_hint", sa.String(length=160), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("worker_registration_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_worker_registration_tokens_token_hash"), ["token_hash"], unique=True
        )

    op.create_table(
        "group_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "user_id"),
    )
    op.create_table(
        "mcp_server_secrets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mcp_server_id", sa.String(length=36), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mcp_server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mcp_server_id"),
    )
    op.create_table(
        "model_catalog",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=240), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "model_id"),
    )
    op.create_table(
        "pipeline_triggers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_id", sa.String(length=36), nullable=False),
        sa.Column("kind", legacy_enum("manual", "cron", "api", name="triggerkind"), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "pipeline_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pipeline_id", "version"),
    )
    op.create_table(
        "provider_secrets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id"),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column(
            "kind", legacy_enum("ai", "script", "mcp", "crewai", name="agentkind"), nullable=False
        ),
        sa.Column("execution_requirement", sa.String(length=20), nullable=False),
        sa.Column(
            "visibility",
            legacy_enum("private", "public", "groups", name="visibility"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=True),
        sa.Column("model_catalog_id", sa.String(length=36), nullable=True),
        sa.Column("mcp_server_id", sa.String(length=36), nullable=True),
        sa.Column("mcp_tool_name", sa.String(length=128), nullable=True),
        sa.Column("draft_config", sa.JSON(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mcp_server_id"],
            ["mcp_servers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["model_catalog_id"],
            ["model_catalog.id"],
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_agents_execution_requirement"), ["execution_requirement"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_agents_mcp_server_id"), ["mcp_server_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_agents_name"), ["name"], unique=False)
        batch_op.create_index(batch_op.f("ix_agents_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_agents_slug"), ["slug"], unique=True)

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("pipeline_id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_version_id", sa.String(length=36), nullable=True),
        sa.Column("trigger_id", sa.String(length=36), nullable=True),
        sa.Column(
            "trigger_kind", legacy_enum("manual", "cron", "api", name="triggerkind"), nullable=False
        ),
        sa.Column("triggered_by", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            legacy_enum("queued", "running", "succeeded", "failed", "cancelled", name="runstatus"),
            nullable=False,
        ),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("graph_snapshot", sa.JSON(), nullable=False),
        sa.Column("engine", sa.String(length=30), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["pipelines.id"],
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_version_id"],
            ["pipeline_versions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["trigger_id"],
            ["pipeline_triggers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pipeline_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pipeline_runs_engine"), ["engine"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_pipeline_runs_pipeline_id"), ["pipeline_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_pipeline_runs_sequence"), ["sequence"], unique=False)

    op.create_table(
        "agent_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "version"),
    )
    op.create_table(
        "step_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("agent_name", sa.String(length=180), nullable=False),
        sa.Column("agent_version_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            legacy_enum("queued", "running", "succeeded", "failed", "cancelled", name="runstatus"),
            nullable=False,
        ),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_action", sa.String(length=300), nullable=False),
        sa.Column("current_action_key", sa.String(length=160), nullable=True),
        sa.Column("current_action_params", sa.JSON(), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
        ),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("step_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_step_runs_run_id"), ["run_id"], unique=False)

    op.create_table(
        "run_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("step_run_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("title_key", sa.String(length=160), nullable=True),
        sa.Column("title_params", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("message_key", sa.String(length=160), nullable=True),
        sa.Column("message_params", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_run_id"], ["step_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("run_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_run_events_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_run_events_kind"), ["kind"], unique=False)
        batch_op.create_index(batch_op.f("ix_run_events_run_id"), ["run_id"], unique=False)

    op.create_table(
        "worker_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("step_run_id", sa.String(length=36), nullable=False),
        sa.Column("executor", sa.String(length=40), nullable=False),
        sa.Column("required_worker_class", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            legacy_enum("queued", "leased", "succeeded", "failed", name="jobstatus"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(length=36), nullable=True),
        sa.Column("lease_hash", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_run_id"], ["step_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_run_id"),
    )
    with op.batch_alter_table("worker_jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_worker_jobs_executor"), ["executor"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_worker_jobs_lease_expires_at"), ["lease_expires_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_worker_jobs_required_worker_class"),
            ["required_worker_class"],
            unique=False,
        )
        batch_op.create_index(batch_op.f("ix_worker_jobs_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_worker_jobs_status"), ["status"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_worker_jobs_step_run_id"), ["step_run_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_worker_jobs_worker_id"), ["worker_id"], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    raise RuntimeError(
        "Baseline downgrade is disabled: it would destroy existing control-plane data"
    )


BASELINE_SCHEMA = {
    "users": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "email": {"nullable": False, "affinity": "String", "length": 320},
            "display_name": {"nullable": False, "affinity": "String", "length": 120},
            "password_hash": {"nullable": False, "affinity": "String", "length": 500},
            "is_root": {"nullable": False, "affinity": "Boolean", "length": None},
            "is_active": {"nullable": False, "affinity": "Boolean", "length": None},
            "locale": {"nullable": False, "affinity": "String", "length": 10},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [],
    },
    "groups": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "name": {"nullable": False, "affinity": "String", "length": 120},
            "description": {"nullable": False, "affinity": "String", "length": None},
            "manager_id": {"nullable": False, "affinity": "String", "length": 36},
        },
        "pk": ["id"],
        "fks": [[["manager_id"], "users", ["id"]]],
    },
    "group_members": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "group_id": {"nullable": False, "affinity": "String", "length": 36},
            "user_id": {"nullable": False, "affinity": "String", "length": 36},
        },
        "pk": ["id"],
        "fks": [[["user_id"], "users", ["id"]], [["group_id"], "groups", ["id"]]],
    },
    "providers": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "name": {"nullable": False, "affinity": "String", "length": 120},
            "kind": {"nullable": False, "affinity": "String", "length": 60},
            "base_url": {"nullable": False, "affinity": "String", "length": 500},
            "enabled": {"nullable": False, "affinity": "Boolean", "length": None},
            "created_by": {"nullable": False, "affinity": "String", "length": 36},
        },
        "pk": ["id"],
        "fks": [[["created_by"], "users", ["id"]]],
    },
    "model_catalog": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "provider_id": {"nullable": False, "affinity": "String", "length": 36},
            "model_id": {"nullable": False, "affinity": "String", "length": 240},
            "display_name": {"nullable": False, "affinity": "String", "length": 240},
            "capabilities": {"nullable": False, "affinity": "JSON", "length": None},
            "enabled": {"nullable": False, "affinity": "Boolean", "length": None},
        },
        "pk": ["id"],
        "fks": [[["provider_id"], "providers", ["id"]]],
    },
    "provider_secrets": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "provider_id": {"nullable": False, "affinity": "String", "length": 36},
            "encrypted_value": {"nullable": False, "affinity": "String", "length": None},
            "updated_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["provider_id"], "providers", ["id"]]],
    },
    "mcp_servers": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "name": {"nullable": False, "affinity": "String", "length": 160},
            "slug": {"nullable": False, "affinity": "String", "length": 160},
            "description": {"nullable": False, "affinity": "String", "length": None},
            "transport": {"nullable": False, "affinity": "String", "length": 30},
            "endpoint": {"nullable": True, "affinity": "String", "length": 1000},
            "command": {"nullable": False, "affinity": "JSON", "length": None},
            "visibility": {
                "nullable": False,
                "affinity": "String",
                "length": 7,
                "enum_values": ["private", "public", "groups"],
            },
            "owner_id": {"nullable": False, "affinity": "String", "length": 36},
            "status": {"nullable": False, "affinity": "String", "length": 20},
            "status_message": {"nullable": False, "affinity": "String", "length": None},
            "protocol_version": {"nullable": True, "affinity": "String", "length": 30},
            "server_info": {"nullable": False, "affinity": "JSON", "length": None},
            "capabilities": {"nullable": False, "affinity": "JSON", "length": None},
            "tools_snapshot": {"nullable": False, "affinity": "JSON", "length": None},
            "last_checked_at": {"nullable": True, "affinity": "DateTime", "length": None},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
            "updated_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["owner_id"], "users", ["id"]]],
    },
    "mcp_server_secrets": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "mcp_server_id": {"nullable": False, "affinity": "String", "length": 36},
            "encrypted_value": {"nullable": False, "affinity": "String", "length": None},
            "updated_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["mcp_server_id"], "mcp_servers", ["id"]]],
    },
    "agents": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "name": {"nullable": False, "affinity": "String", "length": 160},
            "slug": {"nullable": False, "affinity": "String", "length": 160},
            "description": {"nullable": False, "affinity": "String", "length": None},
            "purpose": {"nullable": False, "affinity": "String", "length": None},
            "kind": {
                "nullable": False,
                "affinity": "String",
                "length": 6,
                "enum_values": ["ai", "script", "mcp", "crewai"],
            },
            "execution_requirement": {"nullable": False, "affinity": "String", "length": 20},
            "visibility": {
                "nullable": False,
                "affinity": "String",
                "length": 7,
                "enum_values": ["private", "public", "groups"],
            },
            "owner_id": {"nullable": False, "affinity": "String", "length": 36},
            "provider_id": {"nullable": True, "affinity": "String", "length": 36},
            "model_catalog_id": {"nullable": True, "affinity": "String", "length": 36},
            "mcp_server_id": {"nullable": True, "affinity": "String", "length": 36},
            "mcp_tool_name": {"nullable": True, "affinity": "String", "length": 128},
            "draft_config": {"nullable": False, "affinity": "JSON", "length": None},
            "input_schema": {"nullable": False, "affinity": "JSON", "length": None},
            "output_schema": {"nullable": False, "affinity": "JSON", "length": None},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
            "updated_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [
            [["owner_id"], "users", ["id"]],
            [["model_catalog_id"], "model_catalog", ["id"]],
            [["mcp_server_id"], "mcp_servers", ["id"]],
            [["provider_id"], "providers", ["id"]],
        ],
    },
    "agent_versions": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "agent_id": {"nullable": False, "affinity": "String", "length": 36},
            "version": {"nullable": False, "affinity": "Integer", "length": None},
            "snapshot": {"nullable": False, "affinity": "JSON", "length": None},
            "created_by": {"nullable": False, "affinity": "String", "length": 36},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["agent_id"], "agents", ["id"]], [["created_by"], "users", ["id"]]],
    },
    "acl_entries": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "resource_type": {"nullable": False, "affinity": "String", "length": 40},
            "resource_id": {"nullable": False, "affinity": "String", "length": 36},
            "subject_type": {"nullable": False, "affinity": "String", "length": 20},
            "subject_id": {"nullable": False, "affinity": "String", "length": 36},
            "permissions": {"nullable": False, "affinity": "JSON", "length": None},
        },
        "pk": ["id"],
        "fks": [],
    },
    "pipelines": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "name": {"nullable": False, "affinity": "String", "length": 180},
            "slug": {"nullable": False, "affinity": "String", "length": 180},
            "description": {"nullable": False, "affinity": "String", "length": None},
            "visibility": {
                "nullable": False,
                "affinity": "String",
                "length": 7,
                "enum_values": ["private", "public", "groups"],
            },
            "owner_id": {"nullable": False, "affinity": "String", "length": 36},
            "graph": {"nullable": False, "affinity": "JSON", "length": None},
            "input_schema": {"nullable": False, "affinity": "JSON", "length": None},
            "engine": {"nullable": False, "affinity": "String", "length": 30},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
            "updated_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["owner_id"], "users", ["id"]]],
    },
    "pipeline_versions": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "pipeline_id": {"nullable": False, "affinity": "String", "length": 36},
            "version": {"nullable": False, "affinity": "Integer", "length": None},
            "snapshot": {"nullable": False, "affinity": "JSON", "length": None},
            "created_by": {"nullable": False, "affinity": "String", "length": 36},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["pipeline_id"], "pipelines", ["id"]], [["created_by"], "users", ["id"]]],
    },
    "pipeline_triggers": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "pipeline_id": {"nullable": False, "affinity": "String", "length": 36},
            "kind": {
                "nullable": False,
                "affinity": "String",
                "length": 6,
                "enum_values": ["manual", "cron", "api"],
            },
            "name": {"nullable": False, "affinity": "String", "length": 140},
            "enabled": {"nullable": False, "affinity": "Boolean", "length": None},
            "configuration": {"nullable": False, "affinity": "JSON", "length": None},
            "created_by": {"nullable": False, "affinity": "String", "length": 36},
            "last_fired_at": {"nullable": True, "affinity": "DateTime", "length": None},
            "next_fire_at": {"nullable": True, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["created_by"], "users", ["id"]], [["pipeline_id"], "pipelines", ["id"]]],
    },
    "pipeline_runs": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "sequence": {"nullable": False, "affinity": "Integer", "length": None},
            "pipeline_id": {"nullable": False, "affinity": "String", "length": 36},
            "pipeline_version_id": {"nullable": True, "affinity": "String", "length": 36},
            "trigger_id": {"nullable": True, "affinity": "String", "length": 36},
            "trigger_kind": {
                "nullable": False,
                "affinity": "String",
                "length": 6,
                "enum_values": ["manual", "cron", "api"],
            },
            "triggered_by": {"nullable": True, "affinity": "String", "length": 36},
            "status": {
                "nullable": False,
                "affinity": "String",
                "length": 9,
                "enum_values": ["queued", "running", "succeeded", "failed", "cancelled"],
            },
            "input_payload": {"nullable": False, "affinity": "JSON", "length": None},
            "graph_snapshot": {"nullable": False, "affinity": "JSON", "length": None},
            "engine": {"nullable": False, "affinity": "String", "length": 30},
            "locale": {"nullable": False, "affinity": "String", "length": 10},
            "started_at": {"nullable": True, "affinity": "DateTime", "length": None},
            "finished_at": {"nullable": True, "affinity": "DateTime", "length": None},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [
            [["trigger_id"], "pipeline_triggers", ["id"]],
            [["pipeline_id"], "pipelines", ["id"]],
            [["triggered_by"], "users", ["id"]],
            [["pipeline_version_id"], "pipeline_versions", ["id"]],
        ],
    },
    "step_runs": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "run_id": {"nullable": False, "affinity": "String", "length": 36},
            "node_id": {"nullable": False, "affinity": "String", "length": 100},
            "position": {"nullable": False, "affinity": "Integer", "length": None},
            "title": {"nullable": False, "affinity": "String", "length": 180},
            "agent_name": {"nullable": False, "affinity": "String", "length": 180},
            "agent_version_id": {"nullable": True, "affinity": "String", "length": 36},
            "status": {
                "nullable": False,
                "affinity": "String",
                "length": 9,
                "enum_values": ["queued", "running", "succeeded", "failed", "cancelled"],
            },
            "progress": {"nullable": False, "affinity": "Integer", "length": None},
            "current_action": {"nullable": False, "affinity": "String", "length": 300},
            "current_action_key": {"nullable": True, "affinity": "String", "length": 160},
            "current_action_params": {"nullable": False, "affinity": "JSON", "length": None},
            "input_payload": {"nullable": False, "affinity": "JSON", "length": None},
            "output_payload": {"nullable": False, "affinity": "JSON", "length": None},
            "started_at": {"nullable": True, "affinity": "DateTime", "length": None},
            "finished_at": {"nullable": True, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [
            [["run_id"], "pipeline_runs", ["id"]],
            [["agent_version_id"], "agent_versions", ["id"]],
        ],
    },
    "run_events": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "run_id": {"nullable": False, "affinity": "String", "length": 36},
            "step_run_id": {"nullable": True, "affinity": "String", "length": 36},
            "kind": {"nullable": False, "affinity": "String", "length": 80},
            "level": {"nullable": False, "affinity": "String", "length": 20},
            "title": {"nullable": False, "affinity": "String", "length": 240},
            "title_key": {"nullable": True, "affinity": "String", "length": 160},
            "title_params": {"nullable": False, "affinity": "JSON", "length": None},
            "message": {"nullable": False, "affinity": "String", "length": None},
            "message_key": {"nullable": True, "affinity": "String", "length": 160},
            "message_params": {"nullable": False, "affinity": "JSON", "length": None},
            "payload": {"nullable": False, "affinity": "JSON", "length": None},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["step_run_id"], "step_runs", ["id"]], [["run_id"], "pipeline_runs", ["id"]]],
    },
    "audit_events": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "user_id": {"nullable": False, "affinity": "String", "length": 36},
            "kind": {"nullable": False, "affinity": "String", "length": 80},
            "level": {"nullable": False, "affinity": "String", "length": 20},
            "message": {"nullable": False, "affinity": "String", "length": None},
            "resource_type": {"nullable": True, "affinity": "String", "length": 40},
            "resource_id": {"nullable": True, "affinity": "String", "length": 36},
            "payload": {"nullable": False, "affinity": "JSON", "length": None},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["user_id"], "users", ["id"]]],
    },
    "worker_registration_tokens": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "token_hash": {"nullable": False, "affinity": "String", "length": 64},
            "name_hint": {"nullable": False, "affinity": "String", "length": 160},
            "created_by": {"nullable": False, "affinity": "String", "length": 36},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
            "expires_at": {"nullable": False, "affinity": "DateTime", "length": None},
            "used_at": {"nullable": True, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [[["created_by"], "users", ["id"]]],
    },
    "workers": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "name": {"nullable": False, "affinity": "String", "length": 160},
            "credential_hash": {"nullable": False, "affinity": "String", "length": 64},
            "status": {
                "nullable": False,
                "affinity": "String",
                "length": 8,
                "enum_values": ["online", "offline", "disabled"],
            },
            "worker_class": {"nullable": False, "affinity": "String", "length": 20},
            "executors": {"nullable": False, "affinity": "JSON", "length": None},
            "labels": {"nullable": False, "affinity": "JSON", "length": None},
            "version": {"nullable": False, "affinity": "String", "length": 40},
            "platform": {"nullable": False, "affinity": "String", "length": 80},
            "architecture": {"nullable": False, "affinity": "String", "length": 40},
            "last_seen_at": {"nullable": False, "affinity": "DateTime", "length": None},
            "registered_at": {"nullable": False, "affinity": "DateTime", "length": None},
            "disabled_at": {"nullable": True, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [],
    },
    "worker_jobs": {
        "columns": {
            "id": {"nullable": False, "affinity": "String", "length": 36},
            "run_id": {"nullable": False, "affinity": "String", "length": 36},
            "step_run_id": {"nullable": False, "affinity": "String", "length": 36},
            "executor": {"nullable": False, "affinity": "String", "length": 40},
            "required_worker_class": {"nullable": False, "affinity": "String", "length": 20},
            "status": {
                "nullable": False,
                "affinity": "String",
                "length": 9,
                "enum_values": ["queued", "leased", "succeeded", "failed"],
            },
            "worker_id": {"nullable": True, "affinity": "String", "length": 36},
            "lease_hash": {"nullable": True, "affinity": "String", "length": 64},
            "lease_expires_at": {"nullable": True, "affinity": "DateTime", "length": None},
            "attempts": {"nullable": False, "affinity": "Integer", "length": None},
            "error_message": {"nullable": False, "affinity": "String", "length": None},
            "created_at": {"nullable": False, "affinity": "DateTime", "length": None},
            "finished_at": {"nullable": True, "affinity": "DateTime", "length": None},
        },
        "pk": ["id"],
        "fks": [
            [["step_run_id"], "step_runs", ["id"]],
            [["worker_id"], "workers", ["id"]],
            [["run_id"], "pipeline_runs", ["id"]],
        ],
    },
}


def upgrade() -> None:
    """Create a clean DB or adopt only the verified pre-Alembic schema."""
    inspector = sa.inspect(op.get_bind())
    present = set(inspector.get_table_names()) & set(BASELINE_SCHEMA)
    if not present:
        _create_schema()
        return
    problems = []
    for name, spec in BASELINE_SCHEMA.items():
        if name not in present:
            problems.append(f"missing table {name}")
            continue
        actual = {c["name"]: c for c in inspector.get_columns(name)}
        for column, expected in spec["columns"].items():
            found = actual.get(column)
            if found is None:
                problems.append(f"missing column {name}.{column}")
            elif (
                found["type"]._type_affinity.__name__ != expected["affinity"]
                or found["nullable"] != expected["nullable"]
                or getattr(found["type"], "length", None) != expected["length"]
            ):
                problems.append(f"incompatible column {name}.{column}")
            if (
                found is not None
                and op.get_bind().dialect.name == "postgresql"
                and "enum_values" in expected
                and getattr(found["type"], "enums", []) != expected["enum_values"]
            ):
                problems.append(f"incompatible enum {name}.{column}")
        if inspector.get_pk_constraint(name)["constrained_columns"] != spec["pk"]:
            problems.append(f"incompatible primary key {name}")
        actual_fks = inspector.get_foreign_keys(name)
        for columns, target, target_columns in spec["fks"]:
            if not any(
                f["constrained_columns"] == columns
                and f["referred_table"] == target
                and f["referred_columns"] == target_columns
                for f in actual_fks
            ):
                problems.append(f"missing foreign key {name}.{columns}")
    if problems:
        raise RuntimeError("Cannot adopt legacy schema: " + "; ".join(problems))
