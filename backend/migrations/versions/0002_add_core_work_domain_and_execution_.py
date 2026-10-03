"""add core work domain and execution provenance

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03 11:16:00.947034

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
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("step_runs", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_step_run_pipeline", ["id", "run_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column(
            "visibility",
            legacy_enum("private", "public", "groups", name="visibility"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_project_owner"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "work_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "EPIC",
                "STORY",
                "TASK",
                name="work_item_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "BACKLOG",
                "READY",
                "ASSIGNED",
                "RUNNING",
                "VALIDATING",
                "REVIEW",
                "DONE",
                "BLOCKED",
                "FAILED",
                "CANCELLED",
                "WAITING_FOR_CHILDREN",
                "NEEDS_INPUT",
                "STALE",
                name="work_item_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("owner_type", sa.String(length=10), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_type", sa.String(length=10), nullable=False),
        sa.Column("created_by_id", sa.String(length=100), nullable=False),
        sa.Column("created_from_run_id", sa.String(length=36), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "created_by_type IN ('HUMAN', 'AGENT', 'SERVICE')", name="ck_work_creator_type"
        ),
        sa.CheckConstraint("owner_type IN ('HUMAN', 'AGENT')", name="ck_work_owner_type"),
        sa.CheckConstraint("type <> 'EPIC' OR parent_id IS NULL", name="ck_epic_root"),
        sa.CheckConstraint(
            "(owner_type IS NULL AND owner_id IS NULL) OR (owner_type IS NOT NULL AND owner_id IS NOT NULL)",
            name="ck_work_owner_pair",
        ),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_work_not_own_parent"),
        sa.CheckConstraint("priority BETWEEN 0 AND 4", name="ck_work_priority"),
        sa.CheckConstraint("version >= 1", name="ck_work_version"),
        sa.ForeignKeyConstraint(
            ["parent_id", "project_id"],
            ["work_items.id", "work_items.project_id"],
            name="fk_work_parent_project",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_work_project"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", name="uq_work_item_project"),
    )
    with op.batch_alter_table("work_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_work_items_correlation_id"), ["correlation_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_work_items_parent_id"), ["parent_id"], unique=False)
        batch_op.create_index(
            "ix_work_project_status_priority", ["project_id", "status", "priority"], unique=False
        )

    op.create_table(
        "execution_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=True),
        sa.Column("step_run_id", sa.String(length=36), nullable=True),
        sa.Column("pipeline_version_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("agent_version_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=240), nullable=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            legacy_enum("queued", "running", "succeeded", "failed", "cancelled", name="runstatus"),
            nullable=False,
        ),
        sa.Column("parent_run_id", sa.String(length=36), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "parent_run_id IS NULL OR parent_run_id <> id", name="ck_run_not_own_parent"
        ),
        sa.CheckConstraint(
            "step_run_id IS NULL OR pipeline_run_id IS NOT NULL", name="ck_execution_step_pipeline"
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], name="fk_execution_agent"),
        sa.ForeignKeyConstraint(
            ["agent_version_id"], ["agent_versions.id"], name="fk_execution_agent_version"
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id"], ["execution_runs.id"], name="fk_execution_parent"
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"], ["pipeline_runs.id"], name="fk_execution_pipeline"
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_version_id"], ["pipeline_versions.id"], name="fk_execution_pipeline_version"
        ),
        sa.ForeignKeyConstraint(
            ["step_run_id", "pipeline_run_id"],
            ["step_runs.id", "step_runs.run_id"],
            name="fk_execution_pipeline_step",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["work_items.id"], name="fk_execution_task"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "task_id", name="uq_execution_run_task"),
        sa.UniqueConstraint("step_run_id"),
    )
    with op.batch_alter_table("execution_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_execution_runs_correlation_id"), ["correlation_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_execution_runs_parent_run_id"), ["parent_run_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_execution_runs_pipeline_run_id"), ["pipeline_run_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_execution_runs_task_id"), ["task_id"], unique=False)

    op.create_table(
        "results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("result_type", sa.String(length=80), nullable=False),
        sa.Column("structured_payload", sa.JSON(), nullable=False),
        sa.Column("artifact_references", sa.JSON(), nullable=False),
        sa.Column("validation_status", sa.String(length=12), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("freshness_status", sa.String(length=10), nullable=False),
        sa.Column("freshness_reason", sa.String(length=80), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("source_versions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "freshness_status IN ('CURRENT', 'STALE', 'UNKNOWN')", name="ck_result_freshness"
        ),
        sa.CheckConstraint(
            "review_status IN ('NOT_REQUESTED', 'PENDING', 'APPROVED', 'REJECTED')",
            name="ck_result_review",
        ),
        sa.CheckConstraint(
            "validation_status IN ('PENDING', 'VALID', 'INVALID')", name="ck_result_validation"
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "task_id"],
            ["execution_runs.id", "execution_runs.task_id"],
            name="fk_result_run_task",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["work_items.id"], name="fk_result_task"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("results", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_results_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_results_task_id"), ["task_id"], unique=False)

    with op.batch_alter_table("work_items") as batch_op:
        batch_op.create_foreign_key(
            "fk_work_created_from_run", "execution_runs", ["created_from_run_id"], ["id"]
        )

    # Backfill before imposing NOT NULL; preserve every legacy audit row.
    op.add_column("audit_events", sa.Column("actor_type", sa.String(10), nullable=True))
    op.add_column("audit_events", sa.Column("actor_id", sa.String(100), nullable=True))
    op.execute("UPDATE audit_events SET actor_type = 'HUMAN', actor_id = user_id")
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.alter_column("actor_type", existing_type=sa.String(10), nullable=False)
        batch_op.alter_column("actor_id", existing_type=sa.String(100), nullable=False)
        batch_op.add_column(sa.Column("old_value", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("new_value", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("correlation_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("parent_event_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("project_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("work_item_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("run_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("result_id", sa.String(length=36), nullable=True))
        batch_op.create_check_constraint(
            "ck_audit_actor_identity",
            "(actor_type = 'HUMAN' AND user_id IS NOT NULL AND actor_id = user_id) "
            "OR (actor_type IN ('AGENT', 'SERVICE') AND user_id IS NULL)",
        )
        batch_op.alter_column("user_id", existing_type=sa.VARCHAR(length=36), nullable=True)
        batch_op.create_index(batch_op.f("ix_audit_events_actor_id"), ["actor_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_events_correlation_id"), ["correlation_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_audit_events_project_id"), ["project_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_audit_events_result_id"), ["result_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_events_run_id"), ["run_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_events_work_item_id"), ["work_item_id"], unique=False
        )
        batch_op.create_foreign_key("fk_audit_result", "results", ["result_id"], ["id"])
        batch_op.create_foreign_key("fk_audit_project", "projects", ["project_id"], ["id"])
        batch_op.create_foreign_key(
            "fk_audit_parent_event", "audit_events", ["parent_event_id"], ["id"]
        )
        batch_op.create_foreign_key("fk_audit_execution_run", "execution_runs", ["run_id"], ["id"])
        batch_op.create_foreign_key("fk_audit_work_item", "work_items", ["work_item_id"], ["id"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION reject_audit_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'audit_events is append-only'; END; $$""")
        op.execute("""CREATE TRIGGER audit_events_append_only
            BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events
            FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_mutation()""")
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER audit_events_no_{action.lower()}
                BEFORE {action} ON audit_events BEGIN
                SELECT RAISE(ABORT, 'audit_events is append-only'); END""")


def downgrade() -> None:
    raise RuntimeError(
        "Core domain downgrade is disabled: restore a backup or use a forward migration"
    )
