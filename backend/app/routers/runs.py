import asyncio
import json
import math
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import SessionLocal, get_db
from ..models import (
    JobStatus,
    Pipeline,
    PipelineRun,
    RunEvent,
    RunStatus,
    StepRun,
    User,
    WorkerJob,
)
from ..schemas import EventCreate, EventOut, RunCreate, RunFilterOptions, RunOut, RunPageOut
from ..security import current_user, has_permission, resolve_session_user


router = APIRouter(prefix="/runs", tags=["runs"])
RUN_PAGE_SIZE = 20


def accessible_pipeline_ids(db: Session, user: User) -> list[str]:
    pipelines = list(db.scalars(select(Pipeline)))
    return [
        pipeline.id
        for pipeline in pipelines
        if has_permission(
            db, user, "pipeline", pipeline.id, pipeline.owner_id, pipeline.visibility, "view"
        )
    ]


def run_filter_conditions(
    pipeline_ids: list[str],
    status_filter: Literal["failed", "succeeded"] | None = None,
    pipeline_name: str = "",
    agent_name: str = "",
):
    conditions = [PipelineRun.pipeline_id.in_(pipeline_ids)]
    if status_filter:
        conditions.append(PipelineRun.status == RunStatus(status_filter))
    if pipeline_name.strip():
        normalized_pipeline_name = pipeline_name.strip()
        if normalized_pipeline_name.endswith(" (deleted)"):
            normalized_pipeline_name = normalized_pipeline_name[:-10]
        conditions.append(
            PipelineRun.pipeline.has(Pipeline.name.ilike(f"%{normalized_pipeline_name}%"))
        )
    if agent_name.strip():
        conditions.append(
            PipelineRun.steps.any(StepRun.agent_name.ilike(f"%{agent_name.strip()}%"))
        )
    return conditions


def accessible_run(run_id: str, db: Session, user: User) -> PipelineRun:
    run = db.scalar(
        select(PipelineRun)
        .options(selectinload(PipelineRun.steps), selectinload(PipelineRun.pipeline))
        .where(PipelineRun.id == run_id)
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    pipeline = db.get(Pipeline, run.pipeline_id)
    if not pipeline or not has_permission(
        db, user, "pipeline", pipeline.id, pipeline.owner_id, pipeline.visibility, "view"
    ):
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("", response_model=list[RunOut])
def list_runs(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[PipelineRun]:
    query = (
        select(PipelineRun)
        .options(selectinload(PipelineRun.steps), selectinload(PipelineRun.pipeline))
        .order_by(PipelineRun.created_at.desc())
        .limit(100)
    )
    runs = list(db.scalars(query).unique())
    if user.is_root:
        return runs
    result = []
    for run in runs:
        pipeline = db.get(Pipeline, run.pipeline_id)
        if pipeline and has_permission(
            db, user, "pipeline", pipeline.id, pipeline.owner_id, pipeline.visibility, "view"
        ):
            result.append(run)
    return result


@router.get("/page", response_model=RunPageOut)
def list_runs_page(
    page: int = Query(default=1, ge=1),
    status_filter: Literal["failed", "succeeded"] | None = Query(default=None, alias="status"),
    pipeline: str = Query(default="", max_length=180),
    agent: str = Query(default="", max_length=180),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RunPageOut:
    pipeline_ids = accessible_pipeline_ids(db, user)
    if not pipeline_ids:
        return RunPageOut(items=[], total=0, page=1, page_size=RUN_PAGE_SIZE, pages=1)
    conditions = run_filter_conditions(pipeline_ids, status_filter, pipeline, agent)
    total = db.scalar(select(func.count(PipelineRun.id)).where(*conditions)) or 0
    pages = max(1, math.ceil(total / RUN_PAGE_SIZE))
    current_page = min(page, pages)
    query = (
        select(PipelineRun)
        .options(selectinload(PipelineRun.steps), selectinload(PipelineRun.pipeline))
        .where(*conditions)
        .order_by(PipelineRun.created_at.desc(), PipelineRun.sequence.desc())
        .offset((current_page - 1) * RUN_PAGE_SIZE)
        .limit(RUN_PAGE_SIZE)
    )
    items = list(db.scalars(query).unique())
    return RunPageOut(
        items=items, total=total, page=current_page, page_size=RUN_PAGE_SIZE, pages=pages
    )


@router.get("/filter-options", response_model=RunFilterOptions)
def run_filter_options(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> RunFilterOptions:
    pipeline_ids = accessible_pipeline_ids(db, user)
    if not pipeline_ids:
        return RunFilterOptions()
    pipeline_names = list(
        db.scalars(
            select(Pipeline.name)
            .join(PipelineRun, PipelineRun.pipeline_id == Pipeline.id)
            .where(PipelineRun.pipeline_id.in_(pipeline_ids))
            .distinct()
            .order_by(Pipeline.name)
        )
    )
    agent_names = list(
        db.scalars(
            select(StepRun.agent_name)
            .join(PipelineRun, StepRun.run_id == PipelineRun.id)
            .where(
                PipelineRun.pipeline_id.in_(pipeline_ids),
                StepRun.agent_name != "",
                StepRun.agent_name != "Unassigned agent",
            )
            .distinct()
            .order_by(StepRun.agent_name)
        )
    )
    display_pipeline_names = {
        f"{name.split(':', 2)[-1]} (deleted)" if name.startswith("__deleted__:") else name
        for name in pipeline_names
    }
    return RunFilterOptions(pipelines=sorted(display_pipeline_names), agents=agent_names)


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    run_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> PipelineRun:
    return accessible_run(run_id, db, user)


@router.post("/{run_id}/cancel", response_model=RunOut)
def cancel_run(
    run_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> PipelineRun:
    run = accessible_run(run_id, db, user)
    pipeline = db.get(Pipeline, run.pipeline_id)
    if not pipeline or not has_permission(
        db, user, "pipeline", pipeline.id, pipeline.owner_id, pipeline.visibility, "edit"
    ):
        raise HTTPException(status_code=403, detail="Edit access required")
    if run.status not in {RunStatus.queued, RunStatus.running}:
        raise HTTPException(status_code=409, detail="Only queued or running runs can be cancelled")
    now = datetime.now(timezone.utc)
    run.status = RunStatus.cancelled
    run.finished_at = now
    for step in run.steps:
        if step.status in {RunStatus.queued, RunStatus.running}:
            step.status = RunStatus.cancelled
            step.current_action = "Zrušené používateľom"
            step.current_action_key = "runtime.cancelledByUser"
            step.current_action_params = {}
            step.finished_at = now
    for job in db.scalars(select(WorkerJob).where(WorkerJob.run_id == run.id)):
        if job.status in {JobStatus.queued, JobStatus.leased}:
            job.status = JobStatus.failed
            job.error_message = "Cancelled by user"
            job.lease_hash = None
            job.lease_expires_at = None
            job.finished_at = now
    db.add(
        RunEvent(
            run_id=run.id,
            kind="run.cancelled",
            level="warning",
            title="Run zrušený",
            title_key="runtime.runCancelled",
            message=user.display_name,
            payload={"user_id": user.id},
        )
    )
    db.commit()
    return accessible_run(run_id, db, user)


@router.post("/{run_id}/retry", response_model=RunOut, status_code=201)
def retry_run(
    run_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> PipelineRun:
    run = accessible_run(run_id, db, user)
    if run.status in {RunStatus.queued, RunStatus.running}:
        raise HTTPException(status_code=409, detail="Cancel the active run before retrying it")
    from .pipelines import create_run

    return create_run(
        RunCreate(trigger_kind=run.trigger_kind, input_payload=run.input_payload),
        run.pipeline_id,
        db,
        user,
    )


@router.get("/{run_id}/events", response_model=list[EventOut])
def get_events(
    run_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[RunEvent]:
    accessible_run(run_id, db, user)
    return list(
        db.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.created_at))
    )


@router.post("/{run_id}/events", response_model=EventOut, status_code=201)
def append_event(
    payload: EventCreate,
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RunEvent:
    run = accessible_run(run_id, db, user)
    pipeline = db.get(Pipeline, run.pipeline_id)
    if not has_permission(
        db, user, "pipeline", pipeline.id, pipeline.owner_id, pipeline.visibility, "edit"
    ):
        raise HTTPException(status_code=403, detail="Write access required")
    event = RunEvent(**payload.model_dump(), run_id=run_id)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/{run_id}/stream")
async def stream_events(
    run_id: str, af_session: str | None = Cookie(default=None)
) -> StreamingResponse:
    # A yielded FastAPI dependency lives until a StreamingResponse finishes.
    # Authenticate explicitly so no SQLAlchemy connection is pinned for the
    # lifetime of this potentially long-running SSE stream.
    with SessionLocal() as db:
        user = resolve_session_user(af_session, db)
        accessible_run(run_id, db, user)

    async def generate():
        last_id = None
        for _ in range(600):
            with SessionLocal() as db:
                query = (
                    select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.created_at)
                )
                events = list(db.scalars(query))
                if last_id:
                    index = next((i for i, event in enumerate(events) if event.id == last_id), -1)
                    events = events[index + 1 :]
                for event in events:
                    last_id = event.id
                    data = EventOut.model_validate(event).model_dump(mode="json")
                    yield f"event: run-event\ndata: {json.dumps(data)}\n\n"
            yield ": keep-alive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(generate(), media_type="text/event-stream")
