"""Optional real PostgreSQL acceptance test; uses an isolated disposable schema."""

import os
import uuid
from datetime import datetime, timezone

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.migrations import migration_config, serialized_migration_connection, upgrade_schema
from app.models import (
    Agent,
    AgentKind,
    AuditEvent,
    ExecutionRun,
    Project,
    Result,
    User,
    WorkItem,
    WorkItemType,
)


@pytest.mark.skipif(
    not os.getenv("AF_TEST_POSTGRES_URL"), reason="AF_TEST_POSTGRES_URL not configured"
)
def test_postgres_fresh_schema_legacy_adoption_and_append_only_audit():
    url = os.environ["AF_TEST_POSTGRES_URL"]
    schema = f"af_test_{uuid.uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        config = migration_config()
        with serialized_migration_connection(engine) as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0001")
        with Session(engine) as db:
            user = User(email="pg@example.com", display_name="PG", password_hash="fixture")
            db.add(user)
            db.flush()
            audit = Table("audit_events", MetaData(), autoload_with=engine)
            db.execute(
                audit.insert().values(
                    id="legacy-audit",
                    user_id=user.id,
                    kind="LEGACY",
                    level="info",
                    message="retained",
                    payload={},
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
            user_id = user.id
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE alembic_version")
        upgrade_schema(engine)
        upgrade_schema(engine)
        with Session(engine) as db:
            old = db.get(AuditEvent, "legacy-audit")
            assert old.actor_id == user_id and old.actor_type == "HUMAN"
            project = Project(name="PG", slug="pg", owner_id=user_id)
            agent = Agent(name="Drone", slug="pg-drone", kind=AgentKind.script, owner_id=user_id)
            db.add_all([project, agent])
            db.flush()
            task = WorkItem(
                project_id=project.id,
                type=WorkItemType.TASK,
                title="PG task",
                created_by_type="HUMAN",
                created_by_id=user_id,
            )
            db.add(task)
            db.flush()
            run = ExecutionRun(task_id=task.id, agent_id=agent.id)
            db.add(run)
            db.flush()
            db.add(Result(task_id=task.id, run_id=run.id, result_type="json"))
            db.commit()
            for statement in [
                "UPDATE audit_events SET message='tampered'",
                "DELETE FROM audit_events",
                "TRUNCATE audit_events",
            ]:
                with pytest.raises(DBAPIError), db.begin_nested():
                    db.execute(text(statement))
            assert db.get(AuditEvent, "legacy-audit").message == "retained"
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
        admin.dispose()
