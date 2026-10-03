"""Governed WorkItem mutations; transaction ownership stays with the caller.

Actor is a trusted in-process identity, never an identity supplied by a REST body.
Human/project ACL is reused. Agent/service actions require explicit project grants;
agent credentials/capability enforcement and public Work API arrive in TASK 4–5.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timezone

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .models import (
    AclEntry,
    Agent,
    AuditEvent,
    ExecutionRun,
    Project,
    Result,
    RunStatus,
    User,
    WorkItem,
    WorkItemStatus as S,
    WorkItemType as T,
    uuid4,
)
from .security import has_permission


class LifecycleError(ValueError):
    """Invalid state, hierarchy, or completion prerequisite."""


class LifecycleConflict(LifecycleError):
    """Stale version or pending mutation outside the governed operation."""


@dataclass(frozen=True)
class Actor:
    kind: str
    id: str

    def __post_init__(self):
        if self.kind not in {"HUMAN", "AGENT", "SERVICE"} or not self.id.strip():
            raise ValueError("Actor needs a valid kind and identity")
        if len(self.id) > 100:
            raise ValueError("Actor identity is too long")


TRANSITIONS = {
    S.BACKLOG: {S.READY, S.CANCELLED},
    S.READY: {S.BACKLOG, S.ASSIGNED, S.BLOCKED, S.NEEDS_INPUT, S.CANCELLED},
    S.ASSIGNED: {S.RUNNING, S.READY, S.BLOCKED, S.NEEDS_INPUT, S.FAILED, S.CANCELLED},
    S.RUNNING: {
        S.VALIDATING,
        S.WAITING_FOR_CHILDREN,
        S.BLOCKED,
        S.NEEDS_INPUT,
        S.FAILED,
        S.CANCELLED,
    },
    S.VALIDATING: {S.REVIEW, S.WAITING_FOR_CHILDREN, S.NEEDS_INPUT, S.FAILED, S.CANCELLED},
    S.REVIEW: {S.DONE, S.READY, S.BLOCKED, S.STALE, S.FAILED, S.CANCELLED},
    S.DONE: {S.STALE},
    S.BLOCKED: {S.READY, S.FAILED, S.CANCELLED},
    S.FAILED: {S.READY, S.CANCELLED},
    S.CANCELLED: set(),
    S.WAITING_FOR_CHILDREN: {S.RUNNING, S.VALIDATING, S.BLOCKED, S.FAILED, S.CANCELLED},
    S.NEEDS_INPUT: {S.READY, S.FAILED, S.CANCELLED},
    S.STALE: {S.READY, S.CANCELLED},
}
REASON_STATES = {S.BLOCKED, S.FAILED, S.CANCELLED, S.NEEDS_INPUT, S.STALE}
ACTIVE = {RunStatus.queued, RunStatus.running}


def _authorize(db, project, actor):
    if actor.kind == "HUMAN":
        user = db.get(User, actor.id)
        allowed = (
            user
            and user.is_active
            and has_permission(
                db, user, "project", project.id, project.owner_id, project.visibility, "edit"
            )
        )
    else:
        if actor.kind == "AGENT" and not db.get(Agent, actor.id):
            raise PermissionError("Agent identity unavailable")
        grants = db.scalars(
            select(AclEntry).where(
                AclEntry.resource_type == "project",
                AclEntry.resource_id == project.id,
                AclEntry.subject_type == actor.kind.lower(),
                AclEntry.subject_id == actor.id,
            )
        )
        allowed = any(set(entry.permissions) & {"edit", "manage", "owner"} for entry in grants)
    if not allowed:
        raise PermissionError("Project edit permission required")


def validate_parent(items, item_type, parent_id, item_id=None):
    """Pure hierarchy validation, reused by the upcoming create/update Work service."""
    item_type = T(item_type)
    if parent_id is None:
        return
    parent = items.get(parent_id)
    if parent is None:
        raise LifecycleError("Parent must exist in the same project")
    allowed = {T.EPIC: set(), T.STORY: {T.EPIC}, T.TASK: {T.STORY, T.TASK}}
    if parent.type not in allowed[item_type]:
        raise LifecycleError(f"{item_type.value} cannot have a {parent.type.value} parent")
    visited = {item_id} if item_id else set()
    current = parent
    while current is not None:
        if current.id in visited:
            raise LifecycleError("Hierarchy cycle detected")
        visited.add(current.id)
        if current.parent_id and current.parent_id not in items:
            raise LifecycleError("Parent must exist in the same project")
        current = items.get(current.parent_id)


def validate_hierarchy(items):
    for item in items.values():
        validate_parent(items, item.type, item.parent_id, item.id)


def _descendants(items, root_id):
    children = {}
    for item in items.values():
        children.setdefault(item.parent_id, []).append(item)
    pending = list(children.get(root_id, []))
    seen = {root_id}
    result = []
    while pending:
        item = pending.pop()
        if item.id in seen:
            raise LifecycleError("Hierarchy cycle detected")
        seen.add(item.id)
        result.append(item)
        pending.extend(children.get(item.id, []))
    return result


def derive_status(statuses):
    """Conservative aggregate: cancellation in a mixed scope never silently means done."""
    states = set(statuses)
    if not states:
        return S.BACKLOG
    if states == {S.DONE}:
        return S.DONE
    if states == {S.CANCELLED}:
        return S.CANCELLED
    for status in (S.FAILED, S.BLOCKED, S.STALE, S.NEEDS_INPUT, S.WAITING_FOR_CHILDREN):
        if status in states:
            return status
    if S.CANCELLED in states:
        return S.BLOCKED
    if states <= {S.DONE, S.REVIEW}:
        return S.REVIEW
    if states <= {S.DONE, S.REVIEW, S.VALIDATING}:
        return S.VALIDATING
    if states & {S.RUNNING, S.VALIDATING, S.REVIEW, S.DONE}:
        return S.RUNNING
    if S.ASSIGNED in states:
        return S.ASSIGNED
    if S.READY in states:
        return S.READY
    return S.BACKLOG


def _audit(db, work, actor, kind, old, new, reason, parent_event_id=None, correlation_id=None):
    event = AuditEvent(
        id=uuid4(),
        actor_type=actor.kind,
        actor_id=actor.id,
        user_id=actor.id if actor.kind == "HUMAN" else None,
        kind=kind,
        message=f"{kind}: {work.id}",
        resource_type="work_item",
        resource_id=work.id,
        project_id=work.project_id,
        work_item_id=work.id,
        correlation_id=correlation_id or work.correlation_id,
        old_value=old,
        new_value=new,
        reason=reason,
        parent_event_id=parent_event_id,
    )
    db.add(event)
    # Root event must exist before derived events reference it. A failure rolls
    # state and all audit rows back to the operation's savepoint.
    db.flush()
    return event


def _sync_containers(db, items, actor, root_event, roots):
    affected = set()
    for root_id in roots:
        while root_id is not None:
            if root_id in affected:
                break
            affected.add(root_id)
            root_id = items[root_id].parent_id
    for work in sorted((items[key] for key in affected), key=lambda item: item.id):
        if work.type == T.TASK:
            continue
        descendants = _descendants(items, work.id)
        tasks = [item for item in descendants if item.type == T.TASK]
        # Include empty Story scopes so DONE tasks cannot hide an unplanned Story.
        empty_stories = [
            item
            for item in descendants
            if item.type == T.STORY
            and not any(child.type == T.TASK for child in _descendants(items, item.id))
        ]
        target = derive_status([item.status for item in tasks] + [S.BACKLOG] * len(empty_stories))
        if work.status != target:
            old = {"status": work.status.value, "version": work.version}
            work.status = target
            _audit(
                db,
                work,
                actor,
                "STATUS_DERIVED",
                old,
                {"status": target.value, "version": work.version + 1},
                "Derived from descendant work",
                root_event.id,
                root_event.correlation_id,
            )


@contextmanager
def _operation(db: Session, work_id, actor, expected_version):
    if (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 1
    ):
        raise LifecycleConflict("A positive expected_version is required")
    if any(isinstance(obj, WorkItem) for obj in db.new | db.deleted) or any(
        isinstance(obj, WorkItem) and db.is_modified(obj, include_collections=False)
        for obj in db.dirty
    ):
        raise LifecycleConflict("Flush creation/assignment before calling lifecycle operations")
    project_id = db.scalar(select(WorkItem.project_id).where(WorkItem.id == work_id))
    if project_id is None:
        raise LookupError("Work item not found")
    if db.get_bind().dialect.name == "sqlite":
        # Lock before SAVEPOINT starts a read snapshot; concurrent deferred
        # SQLite readers must not deadlock while upgrading to writer locks.
        try:
            db.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(updated_at=Project.updated_at)
            )
        except OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise LifecycleConflict("Concurrent writer; retry in a new transaction") from exc
            raise
    with db.begin_nested():
        project = db.scalar(select(Project).where(Project.id == project_id).with_for_update())
        _authorize(db, project, actor)
        items = {
            item.id: item
            for item in db.scalars(
                select(WorkItem)
                .where(WorkItem.project_id == project_id)
                .execution_options(populate_existing=True)
            )
        }
        work = items[work_id]
        if work.version != expected_version:
            raise LifecycleConflict("Work item version changed")
        validate_hierarchy(items)
        yield work, items
        db.flush()


def _require_owner(db, work):
    if work.owner_type == "HUMAN":
        owner = db.get(User, work.owner_id)
        if owner and owner.is_active:
            return
    elif work.owner_type == "AGENT" and db.get(Agent, work.owner_id):
        return
    raise LifecycleError("Assigned/running work requires an available owner")


def _guards(db, work, items, target):
    children = _descendants(items, work.id)
    if target in {S.ASSIGNED, S.RUNNING}:
        _require_owner(db, work)
    if target == S.WAITING_FOR_CHILDREN and (
        not children or all(child.status == S.DONE for child in children)
    ):
        raise LifecycleError("Waiting requires unfinished child work")
    if work.status == S.WAITING_FOR_CHILDREN and target in {S.RUNNING, S.VALIDATING}:
        if any(child.status != S.DONE for child in children):
            raise LifecycleError("Child work must be done before parent continuation")
    if target in {S.DONE, S.FAILED, S.CANCELLED}:
        ids = [work.id] + [child.id for child in children]
        active = db.scalar(
            select(ExecutionRun.id)
            .where(ExecutionRun.task_id.in_(ids), ExecutionRun.status.in_(ACTIVE))
            .limit(1)
        )
        if active:
            raise LifecycleError("Finish/cancel active runs before closing work")
    if target in {S.DONE, S.CANCELLED}:
        required = {S.DONE} if target == S.DONE else {S.DONE, S.CANCELLED}
        if any(child.status not in required for child in children):
            raise LifecycleError("Close child work before closing the parent")
    if target == S.DONE:
        latest_run = db.scalar(
            select(ExecutionRun)
            .where(ExecutionRun.task_id == work.id)
            .order_by(ExecutionRun.created_at.desc(), ExecutionRun.id.desc())
            .limit(1)
        )
        latest_result = (
            db.scalar(
                select(Result)
                .where(Result.run_id == latest_run.id)
                .order_by(Result.created_at.desc(), Result.id.desc())
                .limit(1)
            )
            if latest_run
            else None
        )
        if (
            not latest_run
            or latest_run.status != RunStatus.succeeded
            or not latest_result
            or (
                latest_result.validation_status,
                latest_result.review_status,
                latest_result.freshness_status,
            )
            != ("VALID", "APPROVED", "CURRENT")
        ):
            raise LifecycleError("Done requires the latest run's valid, approved, current result")
        latest_ready = db.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.work_item_id == work.id,
                AuditEvent.kind == "STATUS_CHANGED",
                AuditEvent.new_value["status"].as_string() == S.READY.value,
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(1)
        )
        if latest_ready:
            run_time = latest_run.created_at.replace(tzinfo=timezone.utc)
            ready_time = latest_ready.created_at.replace(tzinfo=timezone.utc)
            if run_time < ready_time:
                raise LifecycleError("A retry/rework requires a new run, not an earlier result")


def transition_work_item(
    db: Session,
    work_id: str,
    target: S,
    *,
    actor: Actor,
    expected_version: int,
    reason: str | None = None,
) -> WorkItem:
    target = S(target)
    reason = reason.strip() if reason else None
    if reason and len(reason) > 2000:
        raise LifecycleError("Reason is too long")
    with _operation(db, work_id, actor, expected_version) as (work, items):
        if work.type != T.TASK:
            raise LifecycleError("Epic/Story status is derived; transition descendant Tasks")
        if target not in TRANSITIONS[work.status]:
            raise LifecycleError(f"Invalid transition {work.status.value} -> {target.value}")
        if (
            target in REASON_STATES
            or (
                target == S.READY
                and work.status in {S.REVIEW, S.FAILED, S.BLOCKED, S.NEEDS_INPUT, S.STALE}
            )
        ) and not reason:
            raise LifecycleError("This transition requires a reason")
        _guards(db, work, items, target)
        old = {"status": work.status.value, "version": work.version}
        work.status = target
        event = _audit(
            db,
            work,
            actor,
            "STATUS_CHANGED",
            old,
            {"status": target.value, "version": work.version + 1},
            reason,
        )
        _sync_containers(db, items, actor, event, [work.id])
    return work


def reparent_work_item(
    db: Session,
    work_id: str,
    parent_id: str | None,
    *,
    actor: Actor,
    expected_version: int,
    reason: str,
) -> WorkItem:
    if not reason or not reason.strip() or len(reason) > 2000:
        raise LifecycleError("Reparent requires a reason of up to 2000 characters")
    with _operation(db, work_id, actor, expected_version) as (work, items):
        if work.parent_id == parent_id:
            raise LifecycleError("Parent is unchanged")
        validate_parent(items, work.type, parent_id, work.id)
        scope = [work] + _descendants(items, work.id)
        if any(
            item.status not in {S.BACKLOG, S.READY, S.BLOCKED, S.NEEDS_INPUT, S.STALE}
            for item in scope
        ):
            raise LifecycleError("Only inactive work scopes can be reparented")
        for parent in (items.get(work.parent_id), items.get(parent_id)):
            if parent and parent.type == T.TASK and parent.status in {S.DONE, S.CANCELLED}:
                raise LifecycleError("Cannot change the scope of closed Task work")
        if db.scalar(
            select(ExecutionRun.id)
            .where(
                ExecutionRun.task_id.in_([item.id for item in scope]),
                ExecutionRun.status.in_(ACTIVE),
            )
            .limit(1)
        ):
            raise LifecycleError("Cannot reparent work with active runs")
        old = {"parent_id": work.parent_id, "version": work.version}
        work.parent_id = parent_id
        event = _audit(
            db,
            work,
            actor,
            "PARENT_CHANGED",
            old,
            {"parent_id": parent_id, "version": work.version + 1},
            reason.strip(),
        )
        db.expire(work, ["parent"])
        for parent in (items.get(old["parent_id"]), items.get(parent_id)):
            if parent:
                db.expire(parent, ["children"])
        _sync_containers(db, items, actor, event, [work.id, old["parent_id"], parent_id])
    return work
