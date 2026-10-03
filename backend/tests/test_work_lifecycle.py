"""State transitions, agent actors, hierarchy governance and transaction integrity."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.migrations import upgrade_schema
from app.models import (
    AclEntry,
    AuditEvent,
    ExecutionRun,
    Project,
    Result,
    RunStatus,
    User,
    WorkItem,
    WorkItemStatus as S,
    WorkItemType as T,
)
from app.work_lifecycle import (
    Actor,
    LifecycleConflict,
    LifecycleError,
    reparent_work_item,
    transition_work_item,
)
from test_core_domain import base_objects, item, sqlite_engine


@pytest.fixture
def database(tmp_path):
    engine = sqlite_engine(tmp_path / "lifecycle.db")
    upgrade_schema(engine)
    yield engine
    engine.dispose()


def scope(db):
    user, project, agent = base_objects(db)
    epic = item(db, project, user, T.EPIC)
    story = item(db, project, user, T.STORY, epic)
    task = item(db, project, user, parent=story)
    task.owner_type, task.owner_id = "HUMAN", user.id
    db.flush()
    return Actor("HUMAN", user.id), project, agent, epic, story, task


def move(db, task, target, actor, reason=None):
    return transition_work_item(
        db, task.id, target, actor=actor, expected_version=task.version, reason=reason
    )


def output(
    db,
    task,
    agent,
    *,
    run_status=RunStatus.succeeded,
    validation="VALID",
    review="APPROVED",
    freshness="CURRENT",
    created_at=None,
):
    options = {"created_at": created_at} if created_at else {}
    run = ExecutionRun(task_id=task.id, agent_id=agent.id, status=run_status, **options)
    db.add(run)
    db.flush()
    result = Result(
        task_id=task.id,
        run_id=run.id,
        result_type="json",
        structured_payload={"answer": 42},
        validation_status=validation,
        review_status=review,
        freshness_status=freshness,
    )
    db.add(result)
    db.flush()
    return run, result


def count(db):
    return db.scalar(select(func.count()).select_from(AuditEvent))


def test_full_lifecycle_is_audited_and_containers_follow_descendants(database):
    with Session(database) as db:
        actor, _project, agent, epic, story, task = scope(db)
        for target in [S.READY, S.ASSIGNED, S.RUNNING, S.VALIDATING, S.REVIEW]:
            move(db, task, target, actor)
            assert task.status == story.status == epic.status == target
        output(db, task, agent)
        move(db, task, S.DONE, actor)
        db.commit()
        assert task.status == story.status == epic.status == S.DONE
        events = list(db.scalars(select(AuditEvent)))
        direct = [row for row in events if row.kind == "STATUS_CHANGED"]
        assert len(direct) == 6 and len(events) == 18
        for event in direct:
            assert event.actor_type == "HUMAN" and event.actor_id == actor.id
            assert event.new_value["version"] == event.old_value["version"] + 1
        derived = [row for row in events if row.kind == "STATUS_DERIVED"]
        assert all(row.parent_event_id in {event.id for event in direct} for row in derived)
        assert all(row.correlation_id == task.correlation_id for row in events)


@pytest.mark.parametrize(
    "source,target",
    [
        (S.BACKLOG, S.DONE),
        (S.READY, S.REVIEW),
        (S.RUNNING, S.READY),
        (S.CANCELLED, S.READY),
        (S.STALE, S.DONE),
        (S.READY, S.READY),
    ],
)
def test_invalid_transition_has_no_side_effects(database, source, target):
    with Session(database) as db:
        actor, _project, _agent, _epic, _story, task = scope(db)
        task.status = source
        db.flush()
        before = task.version
        with pytest.raises(LifecycleError, match="Invalid transition"):
            move(db, task, target, actor, "Attempt invalid jump")
        assert task.status == source and task.version == before and count(db) == 0


@pytest.mark.parametrize(
    "source,target",
    [
        (S.READY, S.BLOCKED),
        (S.RUNNING, S.FAILED),
        (S.BACKLOG, S.CANCELLED),
        (S.READY, S.NEEDS_INPUT),
        (S.DONE, S.STALE),
        (S.REVIEW, S.READY),
    ],
)
def test_exceptional_transition_requires_reason(database, source, target):
    with Session(database) as db:
        actor, _project, _agent, _epic, _story, task = scope(db)
        task.status = source
        db.flush()
        with pytest.raises(LifecycleError, match="requires a reason"):
            move(db, task, target, actor)
        assert count(db) == 0
        move(db, task, target, actor, "Documented cause")
        assert task.status == target
        assert (
            db.scalar(select(AuditEvent).where(AuditEvent.kind == "STATUS_CHANGED")).reason
            == "Documented cause"
        )


@pytest.mark.parametrize("source", [S.FAILED, S.BLOCKED, S.NEEDS_INPUT, S.STALE])
def test_recovery_goes_back_through_ready(database, source):
    with Session(database) as db:
        actor, _project, _agent, _epic, _story, task = scope(db)
        task.status = source
        db.flush()
        move(db, task, S.READY, actor, "Dependency resolved; retry")
        assert task.status == S.READY


def test_agent_requires_own_project_authority_not_owners_root_privilege(database):
    with Session(database) as db:
        actor, project, agent, _epic, _story, task = scope(db)
        db.get(User, actor.id).is_root = True
        db.flush()
        chief = Actor("AGENT", agent.id)
        with pytest.raises(PermissionError):
            move(db, task, S.READY, chief)
        assert task.status == S.BACKLOG and count(db) == 0
        db.add(
            AclEntry(
                resource_type="project",
                resource_id=project.id,
                subject_type="agent",
                subject_id=agent.id,
                permissions=["edit"],
            )
        )
        db.flush()
        move(db, task, S.READY, chief)
        event = db.scalar(select(AuditEvent).where(AuditEvent.kind == "STATUS_CHANGED"))
        assert event.actor_type == "AGENT" and event.actor_id == agent.id and event.user_id is None


def test_viewer_and_ungranted_service_cannot_transition(database):
    with Session(database) as db:
        _actor, project, _agent, _epic, _story, task = scope(db)
        outsider = User(email="viewer@example.com", display_name="Viewer", password_hash="fixture")
        db.add(outsider)
        db.flush()
        db.add(
            AclEntry(
                resource_type="project",
                resource_id=project.id,
                subject_type="user",
                subject_id=outsider.id,
                permissions=["view"],
            )
        )
        db.flush()
        for actor in [Actor("HUMAN", outsider.id), Actor("SERVICE", "scheduler")]:
            with pytest.raises(PermissionError):
                move(db, task, S.READY, actor)
        assert count(db) == 0


def test_stale_version_and_direct_container_transition_rejected(database):
    with Session(database) as db:
        actor, _project, _agent, _epic, story, task = scope(db)
        move(db, task, S.READY, actor)
        before = count(db)
        with pytest.raises(LifecycleConflict, match="version changed"):
            transition_work_item(db, task.id, S.ASSIGNED, actor=actor, expected_version=1)
        with pytest.raises(LifecycleError, match="status is derived"):
            move(db, story, S.DONE, actor)
        assert count(db) == before


def test_assignment_requires_owner(database):
    with Session(database) as db:
        actor, _project, _agent, _epic, _story, task = scope(db)
        task.owner_type = task.owner_id = None
        db.flush()
        move(db, task, S.READY, actor)
        with pytest.raises(LifecycleError, match="owner"):
            move(db, task, S.ASSIGNED, actor)


@pytest.mark.parametrize(
    "validation,review,freshness",
    [
        ("PENDING", "APPROVED", "CURRENT"),
        ("INVALID", "APPROVED", "CURRENT"),
        ("VALID", "PENDING", "CURRENT"),
        ("VALID", "REJECTED", "CURRENT"),
        ("VALID", "APPROVED", "UNKNOWN"),
        ("VALID", "APPROVED", "STALE"),
    ],
)
def test_done_requires_valid_approved_current_result(database, validation, review, freshness):
    with Session(database) as db:
        actor, _project, agent, _epic, _story, task = scope(db)
        task.status = S.REVIEW
        db.flush()
        output(db, task, agent, validation=validation, review=review, freshness=freshness)
        with pytest.raises(LifecycleError, match="Done requires"):
            move(db, task, S.DONE, actor)
        assert count(db) == 0 and task.status == S.REVIEW


def test_retry_cannot_reuse_older_approved_result(database):
    with Session(database) as db:
        actor, _project, agent, _epic, _story, task = scope(db)
        task.status = S.REVIEW
        db.flush()
        output(db, task, agent, created_at=datetime.now(timezone.utc) - timedelta(days=1))
        move(db, task, S.READY, actor, "Review requested a rework")
        for state in [S.ASSIGNED, S.RUNNING, S.VALIDATING, S.REVIEW]:
            move(db, task, state, actor)
        with pytest.raises(LifecycleError, match="new run"):
            move(db, task, S.DONE, actor)
        output(db, task, agent)
        move(db, task, S.DONE, actor)
        assert task.status == S.DONE


def test_latest_failed_run_prevents_old_result_from_completing_task(database):
    with Session(database) as db:
        actor, _project, agent, _epic, _story, task = scope(db)
        task.status = S.REVIEW
        db.flush()
        output(db, task, agent, created_at=datetime.now(timezone.utc) - timedelta(days=1))
        output(db, task, agent, run_status=RunStatus.failed)
        with pytest.raises(LifecycleError, match="Done requires"):
            move(db, task, S.DONE, actor)


@pytest.mark.parametrize("target", [S.FAILED, S.CANCELLED, S.DONE])
def test_active_run_must_finish_before_task_closes(database, target):
    with Session(database) as db:
        actor, _project, agent, _epic, _story, task = scope(db)
        task.status = S.REVIEW
        db.flush()
        output(db, task, agent, run_status=RunStatus.running)
        with pytest.raises(LifecycleError, match="active runs"):
            move(db, task, target, actor, "Close work")
        assert count(db) == 0


def test_waiting_parent_continues_only_after_child_is_done(database):
    with Session(database) as db:
        actor, project, _agent, _epic, story, task = scope(db)
        task.status = S.RUNNING
        db.flush()
        child = item(db, project, db.get(User, actor.id), parent=task)
        move(db, task, S.WAITING_FOR_CHILDREN, actor)
        assert story.status == S.WAITING_FOR_CHILDREN
        with pytest.raises(LifecycleError, match="Child work"):
            move(db, task, S.RUNNING, actor)
        child.status = S.DONE  # Fixture of an independently completed managed child.
        db.flush()
        move(db, task, S.RUNNING, actor)
        assert task.status == S.RUNNING


def test_waiting_requires_children_and_parent_done_cannot_hide_unfinished_child(database):
    with Session(database) as db:
        actor, project, agent, _epic, _story, task = scope(db)
        task.status = S.RUNNING
        db.flush()
        with pytest.raises(LifecycleError, match="Waiting requires"):
            move(db, task, S.WAITING_FOR_CHILDREN, actor)
        item(db, project, db.get(User, actor.id), parent=task)
        task.status = S.REVIEW
        db.flush()
        output(db, task, agent)
        with pytest.raises(LifecycleError, match="Close child work"):
            move(db, task, S.DONE, actor)


def test_mixed_done_and_cancelled_scope_is_blocked_not_done(database):
    with Session(database) as db:
        actor, project, agent, epic, story, task = scope(db)
        task.status = S.REVIEW
        db.flush()
        output(db, task, agent)
        other = item(db, project, db.get(User, actor.id), parent=story)
        move(db, task, S.DONE, actor)
        move(db, other, S.CANCELLED, actor, "Removed from scope")
        assert story.status == epic.status == S.BLOCKED


def test_atomic_rollback_includes_derived_statuses_and_preserves_caller_transaction(
    database, monkeypatch
):
    import app.work_lifecycle as lifecycle

    with Session(database) as db:
        actor, _project, _agent, epic, story, task = scope(db)
        db.commit()
        original = lifecycle._sync_containers

        def fail_after_aggregation(*args):
            original(*args)
            raise RuntimeError("Injected consumer failure")

        monkeypatch.setattr(lifecycle, "_sync_containers", fail_after_aggregation)
        with pytest.raises(RuntimeError, match="Injected"):
            move(db, task, S.READY, actor)
        assert task.status == story.status == epic.status == S.BACKLOG and count(db) == 0
        monkeypatch.setattr(lifecycle, "_sync_containers", original)
        move(db, task, S.READY, actor)
        db.rollback()  # The domain service never commits on behalf of its caller.
        assert task.status == story.status == epic.status == S.BACKLOG and count(db) == 0


def test_reparent_recomputes_both_epics_and_invalidates_cached_relationships(database):
    with Session(database) as db:
        actor, project, _agent, old, story, task = scope(db)
        new = item(db, project, db.get(User, actor.id), T.EPIC)
        move(db, task, S.READY, actor)
        assert story.parent.id == old.id and story in old.children
        reparent_work_item(
            db,
            story.id,
            new.id,
            actor=actor,
            expected_version=story.version,
            reason="Move planning scope",
        )
        assert story.parent.id == new.id and story not in old.children
        assert old.status == S.BACKLOG and new.status == S.READY
        assert (
            db.scalar(select(AuditEvent).where(AuditEvent.kind == "PARENT_CHANGED")).reason
            == "Move planning scope"
        )


@pytest.mark.parametrize(
    "child_type,parent_type", [(T.EPIC, T.STORY), (T.STORY, T.TASK), (T.TASK, T.EPIC)]
)
def test_wrong_parent_type_rejected(database, child_type, parent_type):
    with Session(database) as db:
        actor, project, _agent, _epic, _story, _task = scope(db)
        child = item(db, project, db.get(User, actor.id), child_type)
        parent = item(db, project, db.get(User, actor.id), parent_type)
        with pytest.raises(LifecycleError, match="cannot have"):
            reparent_work_item(
                db,
                child.id,
                parent.id,
                actor=actor,
                expected_version=child.version,
                reason="Invalid parent",
            )
        assert child.parent_id is None and count(db) == 0


def test_nested_task_cycle_and_cross_project_parent_rejected(database):
    with Session(database) as db:
        actor, project, _agent, _epic, _story, task = scope(db)
        child = item(db, project, db.get(User, actor.id), parent=task)
        with pytest.raises(LifecycleError, match="cycle"):
            reparent_work_item(
                db,
                task.id,
                child.id,
                actor=actor,
                expected_version=task.version,
                reason="Cycle attempt",
            )
        other = Project(name="Other", slug="other", owner_id=actor.id)
        db.add(other)
        db.flush()
        foreign = item(db, other, db.get(User, actor.id))
        with pytest.raises(LifecycleError, match="same project"):
            reparent_work_item(
                db,
                task.id,
                foreign.id,
                actor=actor,
                expected_version=task.version,
                reason="Cross-project attempt",
            )
        assert count(db) == 0


def test_running_scope_cannot_be_reparented(database):
    with Session(database) as db:
        actor, project, _agent, _epic, _story, task = scope(db)
        parent = item(db, project, db.get(User, actor.id))
        for state in [S.READY, S.ASSIGNED, S.RUNNING]:
            move(db, task, state, actor)
        before = count(db)
        with pytest.raises(LifecycleError, match="inactive"):
            reparent_work_item(
                db,
                task.id,
                parent.id,
                actor=actor,
                expected_version=task.version,
                reason="Move live work",
            )
        assert count(db) == before


def test_simultaneous_writers_cannot_duplicate_a_transition(database):
    with Session(database) as db:
        actor, _project, _agent, _epic, _story, task = scope(db)
        db.commit()
        task_id, version = task.id, task.version
    barrier = Barrier(2)

    def writer():
        with Session(database) as db:
            barrier.wait(timeout=5)
            try:
                transition_work_item(db, task_id, S.READY, actor=actor, expected_version=version)
                db.commit()
                return "changed"
            except LifecycleConflict:
                db.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: writer(), range(2)))
    assert sorted(outcomes) == ["changed", "conflict"]
    with Session(database) as db:
        assert db.get(WorkItem, task_id).version == version + 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.kind == "STATUS_CHANGED")
            )
            == 1
        )
