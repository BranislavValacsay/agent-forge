from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..contracts import validate_graph
from ..execution import execution_spec_for_node
from ..models import Pipeline, PipelineRun, PipelineTrigger, RunStatus, StepRun, User, WorkerJob
from ..orchestration import start_langgraph_run
from ..schemas import PipelineCreate, PipelineOut, PipelineValidationOut, RunCreate, RunOut, TriggerCreate, TriggerOut
from ..security import current_user, has_permission


router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def ordered_nodes(graph: dict) -> list[dict]:
    """Stable topological order from control and value edges; x-position breaks ties."""
    nodes = graph.get("nodes", [])
    by_id = {node.get("id"): node for node in nodes}
    indegree = {node_id: 0 for node_id in by_id}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    for edge in graph.get("edges", []):
        source, target = edge.get("source"), edge.get("target")
        if source in by_id and target in by_id and target not in outgoing[source]:
            outgoing[source].append(target)
            indegree[target] += 1
    def key(node_id: str) -> float:
        return by_id[node_id].get("position", {}).get("x", 0)
    ready = sorted((node_id for node_id, degree in indegree.items() if degree == 0), key=key)
    result: list[dict] = []
    while ready:
        node_id = ready.pop(0)
        result.append(by_id[node_id])
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=key)
    return result if len(result) == len(nodes) else sorted(nodes, key=lambda node: node.get("position", {}).get("x", 0))


def get_accessible(pipeline_id: str, db: Session, user: User, write: bool = False) -> Pipeline:
    pipeline = db.get(Pipeline, pipeline_id)
    permission = "edit" if write else "view"
    allowed = pipeline and not pipeline.name.startswith("__deleted__:") and has_permission(db, user, "pipeline", pipeline.id, pipeline.owner_id, pipeline.visibility, permission)
    if not allowed:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return pipeline


@router.get("", response_model=list[PipelineOut])
def list_pipelines(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Pipeline]:
    pipelines = list(db.scalars(select(Pipeline).order_by(Pipeline.updated_at.desc())))
    return [pipeline for pipeline in pipelines if not pipeline.name.startswith("__deleted__:") and has_permission(db, user, "pipeline", pipeline.id, pipeline.owner_id, pipeline.visibility, "view")]


@router.post("", response_model=PipelineOut, status_code=status.HTTP_201_CREATED)
def create_pipeline(payload: PipelineCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Pipeline:
    errors, _ = validate_graph(payload.graph)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    pipeline = Pipeline(**payload.model_dump(), owner_id=user.id)
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.post("/validate-draft", response_model=PipelineValidationOut)
def validate_pipeline_draft(payload: PipelineCreate, user: User = Depends(current_user)) -> PipelineValidationOut:
    errors, warnings = validate_graph(payload.graph)
    return PipelineValidationOut(valid=not errors, errors=errors, warnings=warnings)


@router.get("/{pipeline_id}", response_model=PipelineOut)
def get_pipeline(pipeline_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Pipeline:
    return get_accessible(pipeline_id, db, user)


@router.put("/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(payload: PipelineCreate, pipeline_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Pipeline:
    pipeline = get_accessible(pipeline_id, db, user, write=True)
    errors, _ = validate_graph(payload.graph)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    for key, value in payload.model_dump().items():
        setattr(pipeline, key, value)
    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.delete("/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> None:
    pipeline = get_accessible(pipeline_id, db, user, write=True)
    original_name = pipeline.name
    pipeline.name = f"__deleted__:{pipeline.id}:{original_name}"
    pipeline.slug = f"deleted-{pipeline.id}"
    pipeline.graph = {"nodes": [], "edges": []}
    for trigger in db.scalars(select(PipelineTrigger).where(PipelineTrigger.pipeline_id == pipeline.id)):
        trigger.enabled = False
    db.commit()


@router.get("/{pipeline_id}/triggers", response_model=list[TriggerOut])
def list_triggers(pipeline_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[PipelineTrigger]:
    get_accessible(pipeline_id, db, user)
    return list(db.scalars(select(PipelineTrigger).where(PipelineTrigger.pipeline_id == pipeline_id)))


@router.post("/{pipeline_id}/triggers", response_model=TriggerOut, status_code=201)
def create_trigger(payload: TriggerCreate, pipeline_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> PipelineTrigger:
    get_accessible(pipeline_id, db, user, write=True)
    trigger = PipelineTrigger(**payload.model_dump(), pipeline_id=pipeline_id, created_by=user.id)
    db.add(trigger)
    db.commit()
    db.refresh(trigger)
    return trigger


@router.post("/{pipeline_id}/runs", response_model=RunOut, status_code=201)
def create_run(payload: RunCreate, pipeline_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> PipelineRun:
    pipeline = get_accessible(pipeline_id, db, user)
    if not has_permission(db, user, "pipeline", pipeline.id, pipeline.owner_id, pipeline.visibility, "run"):
        raise HTTPException(status_code=403, detail="Run access required")
    errors, _ = validate_graph(pipeline.graph)
    if errors:
        raise HTTPException(status_code=409, detail={"message": "Pipeline graph is invalid", "errors": errors})
    sequence = (db.scalar(select(func.max(PipelineRun.sequence))) or 0) + 1
    run = PipelineRun(
        sequence=sequence,
        pipeline_id=pipeline.id,
        trigger_id=payload.trigger_id,
        trigger_kind=payload.trigger_kind,
        triggered_by=user.id,
        status=RunStatus.queued,
        input_payload=payload.input_payload,
        graph_snapshot=pipeline.graph,
        engine=pipeline.engine,
        locale=user.locale,
    )
    db.add(run)
    db.flush()
    nodes = ordered_nodes(pipeline.graph)
    for index, node in enumerate(nodes):
        data = node.get("data", {})
        step = StepRun(
                run_id=run.id,
                node_id=node.get("id", f"node-{index}"),
                position=index,
                title=data.get("label", f"Step {index + 1}"),
                agent_name=data.get("agentName", "Unassigned agent"),
                status=RunStatus.queued,
                input_payload=payload.input_payload if index == 0 else {},
            )
        db.add(step)
        db.flush()
        if pipeline.engine == "legacy":
            spec = execution_spec_for_node(db, node)
            step.current_action = f"Čaká na {spec.required_worker_class.upper()} worker s executorom: {spec.executor}"
            step.current_action_key = "runtime.waitingWorker"
            step.current_action_params = {"worker_class": spec.required_worker_class.upper(), "executor": spec.executor}
            db.add(WorkerJob(run_id=run.id, step_run_id=step.id, executor=spec.executor, required_worker_class=spec.required_worker_class))
    if pipeline.engine == "langgraph":
        db.flush()
        db.refresh(run, attribute_names=["steps"])
        start_langgraph_run(db, run)
    db.commit()
    return db.scalar(select(PipelineRun).options(selectinload(PipelineRun.steps), selectinload(PipelineRun.pipeline)).where(PipelineRun.id == run.id))
