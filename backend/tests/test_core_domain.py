"""Core schema acceptance: real migrations and DB-enforced integrity, not mocked models."""

from datetime import datetime, timezone

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, create_engine, event, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.migrations import (
    migration_config,
    require_current_schema,
    serialized_migration_connection,
    upgrade_schema,
)
from app.models import (
    Agent,
    AgentKind,
    AuditEvent,
    ExecutionRun,
    Pipeline,
    PipelineRun,
    Project,
    Result,
    RunStatus,
    StepRun,
    TriggerKind,
    User,
    WorkItem,
    WorkItemStatus,
    WorkItemType,
)


def sqlite_engine(path):
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def enable_fks(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


@pytest.fixture
def database(tmp_path):
    engine = sqlite_engine(tmp_path / "core.db")
    upgrade_schema(engine)
    yield engine
    engine.dispose()


def base_objects(db):
    user = User(email="core@example.com", display_name="Core", password_hash="fixture")
    db.add(user)
    db.flush()
    project = Project(name="Core", slug="core", owner_id=user.id)
    agent = Agent(name="Drone", slug="drone", kind=AgentKind.script, owner_id=user.id)
    db.add_all([project, agent])
    db.flush()
    return user, project, agent


def item(db, project, user, kind=WorkItemType.TASK, parent=None):
    work = WorkItem(
        project_id=project.id,
        parent_id=parent.id if parent else None,
        type=kind,
        title=kind.value,
        created_by_type="HUMAN",
        created_by_id=user.id,
    )
    db.add(work)
    db.flush()
    return work


def test_hierarchy_run_results_and_audit_are_persistent(database):
    with Session(database) as db:
        user, project, agent = base_objects(db)
        epic = item(db, project, user, WorkItemType.EPIC)
        story = item(db, project, user, WorkItemType.STORY, epic)
        task = item(db, project, user, parent=story)
        delegated = item(db, project, user, parent=task)
        run = ExecutionRun(
            task_id=task.id,
            agent_id=agent.id,
            correlation_id=task.correlation_id,
            input_snapshot={"document": "test"},
        )
        db.add(run)
        db.flush()
        child = ExecutionRun(
            task_id=delegated.id,
            agent_id=agent.id,
            parent_run_id=run.id,
            correlation_id=task.correlation_id,
        )
        db.add(child)
        db.flush()
        delegated.created_from_run_id = run.id
        result = Result(
            task_id=delegated.id,
            run_id=child.id,
            result_type="structured",
            structured_payload={"answer": 42},
            source_versions={"source": "v1"},
        )
        db.add(result)
        db.flush()
        audit = AuditEvent(
            actor_type="AGENT",
            actor_id=agent.id,
            kind="RESULT_CREATED",
            message="Created result",
            resource_type="result",
            resource_id=result.id,
            project_id=project.id,
            work_item_id=delegated.id,
            run_id=child.id,
            result_id=result.id,
            correlation_id=task.correlation_id,
            new_value={"answer": 42},
        )
        db.add(audit)
        db.commit()
        epic_id, task_id, result_id, audit_id = epic.id, task.id, result.id, audit.id
    with Session(database) as db:
        epic = db.get(WorkItem, epic_id)
        assert epic.children[0].children[0].id == task_id
        assert epic.children[0].children[0].children[0].created_from_run_id is not None
        result = db.get(Result, result_id)
        assert result.run.parent.task.id == task_id
        assert result.structured_payload == {"answer": 42}
        assert result.validation_status == "PENDING"
        assert result.review_status == "NOT_REQUESTED"
        assert result.freshness_status == "UNKNOWN"
        assert result.run.task.status == WorkItemStatus.BACKLOG
        assert db.get(AuditEvent, audit_id).result_id == result.id


def test_cross_project_parent_and_result_from_other_task_are_rejected(database):
    with Session(database) as db:
        user, project, agent = base_objects(db)
        parent = item(db, project, user)
        other = Project(name="Other", slug="other", owner_id=user.id)
        db.add(other)
        db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            item(db, other, user, parent=parent)
        task = item(db, project, user)
        run = ExecutionRun(task_id=parent.id, agent_id=agent.id)
        db.add(run)
        db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(Result(task_id=task.id, run_id=run.id, result_type="wrong"))
            db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            db.delete(parent)
            db.flush()


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "INVALID"},
        {"status": "INVALID"},
        {"priority": 5},
        {"owner_type": "AGENT", "owner_id": None},
        {"created_by_type": "INVALID"},
    ],
)
def test_invalid_core_values_rejected_by_database(database, changes):
    with Session(database) as db:
        user, project, _agent = base_objects(db)
        work = item(db, project, user)
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(update(WorkItem).where(WorkItem.id == work.id).values(**changes))


def test_step_bridge_cannot_reference_another_pipeline_run(database):
    with Session(database) as db:
        user, project, agent = base_objects(db)
        task = item(db, project, user)
        pipeline = Pipeline(name="Existing", slug="existing", owner_id=user.id)
        db.add(pipeline)
        db.flush()
        runs = [
            PipelineRun(
                sequence=n,
                pipeline_id=pipeline.id,
                trigger_kind=TriggerKind.manual,
                graph_snapshot={"nodes": [], "edges": []},
            )
            for n in [1, 2]
        ]
        db.add_all(runs)
        db.flush()
        step = StepRun(
            run_id=runs[0].id, node_id="drone", position=0, title="Drone", agent_name="Drone"
        )
        db.add(step)
        db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                ExecutionRun(
                    task_id=task.id,
                    agent_id=agent.id,
                    step_run_id=step.id,
                    pipeline_run_id=runs[1].id,
                )
            )
            db.flush()
        linked = ExecutionRun(
            task_id=task.id, agent_id=agent.id, step_run_id=step.id, pipeline_run_id=runs[0].id
        )
        db.add(linked)
        db.flush()
        assert db.get(ExecutionRun, linked.id).pipeline_run_id == runs[0].id


def test_optimistic_version_rejects_lost_update(database):
    with Session(database) as db:
        user, project, _agent = base_objects(db)
        task = item(db, project, user)
        db.commit()
        task_id = task.id
    with Session(database) as first, Session(database) as second:
        a, b = first.get(WorkItem, task_id), second.get(WorkItem, task_id)
        a.title = "First update"
        first.commit()
        assert a.version == 2
        b.title = "Lost update"
        with pytest.raises(StaleDataError):
            second.commit()


def test_audit_is_append_only_and_actor_cannot_impersonate_user(database):
    with Session(database) as db:
        user, _project, agent = base_objects(db)
        row = AuditEvent(
            user_id=user.id,
            actor_type="HUMAN",
            actor_id=user.id,
            kind="CREATED",
            message="Original",
        )
        db.add(row)
        db.commit()
        audit_id = row.id
        for sql in [
            "UPDATE audit_events SET message = 'tampered' WHERE id = :id",
            "DELETE FROM audit_events WHERE id = :id",
        ]:
            with pytest.raises(IntegrityError), db.begin_nested():
                db.execute(text(sql), {"id": audit_id})
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                AuditEvent(
                    user_id=user.id,
                    actor_type="HUMAN",
                    actor_id=agent.id,
                    kind="SPOOFED",
                    message="Wrong actor",
                )
            )
            db.flush()
        assert db.get(AuditEvent, audit_id).message == "Original"


def test_legacy_upgrade_preserves_pipeline_step_and_backfills_audit(tmp_path):
    engine = sqlite_engine(tmp_path / "legacy.db")
    config = migration_config()
    with serialized_migration_connection(engine) as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
    # Simulate the pre-Alembic installation with real legacy records.
    with Session(engine) as db:
        user = User(email="old@example.com", display_name="Old", password_hash="fixture")
        db.add(user)
        db.flush()
        pipeline = Pipeline(name="Old", slug="old", owner_id=user.id)
        db.add(pipeline)
        db.flush()
        run = PipelineRun(
            sequence=1,
            pipeline_id=pipeline.id,
            trigger_kind=TriggerKind.manual,
            status=RunStatus.succeeded,
            graph_snapshot={"nodes": [], "edges": []},
        )
        db.add(run)
        db.flush()
        step = StepRun(
            run_id=run.id,
            node_id="old",
            position=0,
            title="Old",
            agent_name="Old",
            output_payload={"retained": True},
            status=RunStatus.succeeded,
        )
        db.add(step)
        db.flush()
        old_audit = Table("audit_events", MetaData(), autoload_with=engine)
        db.execute(
            old_audit.insert().values(
                id="old-audit",
                user_id=user.id,
                kind="OLD",
                level="info",
                message="Retain me",
                payload={"old": True},
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        user_id, run_id, step_id = user.id, run.id, step.id
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE alembic_version")
    with pytest.raises(RuntimeError, match="outdated"):
        require_current_schema(engine)
    upgrade_schema(engine)
    upgrade_schema(engine)  # Restart/retry must not duplicate or mutate legacy records.
    require_current_schema(engine)
    with Session(engine) as db:
        assert db.get(PipelineRun, run_id).status == RunStatus.succeeded
        assert db.get(StepRun, step_id).output_payload == {"retained": True}
        audit = db.get(AuditEvent, "old-audit")
        assert audit.actor_type == "HUMAN" and audit.actor_id == user_id
        assert audit.message == "Retain me" and audit.payload == {"old": True}
        assert db.scalar(select(AuditEvent.id)) == "old-audit"
    engine.dispose()


def test_partial_legacy_schema_is_not_silently_stamped(tmp_path):
    engine = sqlite_engine(tmp_path / "partial.db")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO users (id) VALUES ('preserve')")
    with pytest.raises(RuntimeError, match="Cannot adopt legacy schema"):
        upgrade_schema(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT id FROM users").scalar() == "preserve"
        assert "work_items" not in inspect(connection).get_table_names()
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    engine.dispose()


def test_destructive_downgrade_refused_without_losing_history(database):
    config = migration_config()
    with pytest.raises(RuntimeError, match="restore a backup"):
        with serialized_migration_connection(database) as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0001")
    require_current_schema(database)
    assert "work_items" in inspect(database).get_table_names()
