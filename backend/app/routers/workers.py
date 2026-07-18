from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..contracts import assign_at, edge_mapping, graph_predecessors, value_at
from ..database import get_db
from ..orchestration import advance_langgraph_run
from ..models import (
    Agent,
    JobStatus,
    ModelCatalog,
    McpServer,
    McpServerSecret,
    PipelineRun,
    Provider,
    ProviderSecret,
    RunEvent,
    RunStatus,
    StepRun,
    User,
    Worker,
    WorkerJob,
    WorkerRegistrationToken,
    WorkerStatus,
)
from ..schemas import (
    WorkerCredentials,
    WorkerHeartbeat,
    WorkerJobComplete,
    WorkerJobEvent,
    WorkerJobOut,
    WorkerOut,
    WorkerRegister,
    WorkerRegistrationTokenCreate,
    WorkerRegistrationTokenOut,
)
from ..security import create_opaque_token, current_user, decrypt_secret, hash_token


admin_router = APIRouter(prefix="/workers", tags=["workers"])
worker_router = APIRouter(prefix="/worker", tags=["worker protocol"])
LEASE_SECONDS = 90


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_root(user: User) -> None:
    if not user.is_root:
        raise HTTPException(status_code=403, detail="Root access required")


def as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def authenticated_worker(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Worker:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Worker token required")
    worker = db.scalar(
        select(Worker).where(Worker.credential_hash == hash_token(authorization[7:]))
    )
    if not worker or worker.status == WorkerStatus.disabled:
        raise HTTPException(status_code=401, detail="Invalid or disabled worker")
    return worker


def public_worker(worker: Worker) -> Worker:
    if worker.status != WorkerStatus.disabled and utcnow() - as_aware(
        worker.last_seen_at
    ) > timedelta(seconds=45):
        worker.status = WorkerStatus.offline
    return worker


@admin_router.get("", response_model=list[WorkerOut])
def list_workers(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Worker]:
    require_root(user)
    workers = list(db.scalars(select(Worker).order_by(Worker.registered_at.desc())))
    for worker in workers:
        public_worker(worker)
    db.commit()
    return workers


@admin_router.post(
    "/registration-tokens", response_model=WorkerRegistrationTokenOut, status_code=201
)
def create_registration_token(
    payload: WorkerRegistrationTokenCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> WorkerRegistrationTokenOut:
    require_root(user)
    raw = create_opaque_token("afreg")
    expires_at = utcnow() + timedelta(minutes=payload.expires_in_minutes)
    db.add(
        WorkerRegistrationToken(
            token_hash=hash_token(raw),
            name_hint=payload.name_hint,
            created_by=user.id,
            expires_at=expires_at,
        )
    )
    db.commit()
    return WorkerRegistrationTokenOut(token=raw, expires_at=expires_at)


def get_worker_or_404(worker_id: str, db: Session) -> Worker:
    worker = db.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker


@admin_router.post("/{worker_id}/disable", status_code=204)
def disable_worker(
    worker_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    require_root(user)
    worker = get_worker_or_404(worker_id, db)
    worker.status = WorkerStatus.disabled
    worker.disabled_at = utcnow()
    db.commit()


@admin_router.post("/{worker_id}/enable", status_code=204)
def enable_worker(
    worker_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    require_root(user)
    worker = get_worker_or_404(worker_id, db)
    worker.status = WorkerStatus.offline
    worker.disabled_at = None
    db.commit()


@admin_router.delete("/{worker_id}", status_code=204)
def delete_worker(
    worker_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    require_root(user)
    worker = get_worker_or_404(worker_id, db)
    jobs = list(db.scalars(select(WorkerJob).where(WorkerJob.worker_id == worker.id)))
    for job in jobs:
        if job.status == JobStatus.leased:
            job.status = JobStatus.queued
            step = db.get(StepRun, job.step_run_id)
            if step and step.status == RunStatus.running:
                step.status = RunStatus.queued
                step.progress = 0
                step.current_action = f"Worker {worker.name} bol odstránený; čaká na iný worker"
        job.worker_id = None
        job.lease_hash = None
        job.lease_expires_at = None
    db.flush()
    db.delete(worker)
    db.commit()


@worker_router.post("/register", response_model=WorkerCredentials, status_code=201)
def register_worker(payload: WorkerRegister, db: Session = Depends(get_db)) -> WorkerCredentials:
    registration = db.scalar(
        select(WorkerRegistrationToken).where(
            WorkerRegistrationToken.token_hash == hash_token(payload.registration_token)
        )
    )
    if not registration or registration.used_at or as_aware(registration.expires_at) < utcnow():
        raise HTTPException(
            status_code=401, detail="Registration token is invalid, expired, or already used"
        )
    credential = create_opaque_token("afwrk")
    worker = Worker(
        name=payload.name,
        credential_hash=hash_token(credential),
        worker_class=payload.worker_class,
        executors=sorted(set(payload.executors)),
        labels=payload.labels,
        version=payload.version,
        platform=payload.platform,
        architecture=payload.architecture,
        status=WorkerStatus.online,
    )
    registration.used_at = utcnow()
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return WorkerCredentials(worker_id=worker.id, worker_token=credential)


@worker_router.post("/heartbeat", status_code=204)
def heartbeat(
    payload: WorkerHeartbeat,
    db: Session = Depends(get_db),
    worker: Worker = Depends(authenticated_worker),
) -> None:
    worker.last_seen_at = utcnow()
    worker.status = WorkerStatus.online
    worker.version = payload.version
    if payload.executors:
        worker.executors = sorted(set(payload.executors))
    db.commit()


def _step_input(db: Session, run: PipelineRun, step: StepRun) -> dict:
    graph = run.graph_snapshot or {}
    edges = [
        edge
        for edge in graph.get("edges", [])
        if edge.get("target") == step.node_id and (edge.get("data") or {}).get("kind") != "control"
    ]
    if not edges:
        return dict(run.input_payload or {})
    result: dict = {}
    assigned_targets: set[str] = set()
    for edge in edges:
        source_step = db.scalar(
            select(StepRun).where(StepRun.run_id == run.id, StepRun.node_id == edge.get("source"))
        )
        mapping = edge_mapping(edge)
        if not source_step or not mapping:
            continue
        target_path = mapping.get("target")
        if not isinstance(target_path, str) or not target_path:
            raise ValueError("Dátové spojenie nemá cieľový názov vstupu")
        if target_path in assigned_targets:
            raise ValueError(f"Viac vetiev zapisuje do rovnakého vstupu '{target_path}'")
        try:
            assign_at(
                result,
                mapping["target"],
                deepcopy(value_at(source_step.output_payload or {}, mapping["source"])),
            )
            assigned_targets.add(target_path)
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"Mapovanie {mapping.get('source')} → {mapping.get('target')} zlyhalo: {exc}"
            ) from exc
    return result


def _step_is_ready(db: Session, run: PipelineRun, step: StepRun) -> bool:
    """A DAG step is ready once all of its direct predecessors succeeded."""
    if run.engine == "langgraph":
        # LangGraph creates WorkerJobs only for its current durable frontier.
        return True
    predecessor_ids = graph_predecessors(run.graph_snapshot or {}, step.node_id)
    if not predecessor_ids:
        return True
    states = {
        item.node_id: item.status
        for item in db.scalars(
            select(StepRun).where(StepRun.run_id == run.id, StepRun.node_id.in_(predecessor_ids))
        )
    }
    return predecessor_ids == states.keys() and all(
        status == RunStatus.succeeded for status in states.values()
    )


def _job_config(db: Session, run: PipelineRun, step: StepRun, executor: str) -> dict:
    node = next(
        (
            node
            for node in (run.graph_snapshot or {}).get("nodes", [])
            if node.get("id") == step.node_id
        ),
        {},
    )
    data = node.get("data") or {}
    node_inputs = data.get("inputs", [])
    node_outputs = data.get("outputs", [])
    config = {
        "node_kind": data.get("nodeKind", "agent"),
        "node_config": data.get("config") or {},
        "input_schema": {
            "type": "object",
            "properties": {
                port["name"]: {"x-agentforge-type": port.get("type", "any")} for port in node_inputs
            },
            "required": [port["name"] for port in node_inputs if port.get("required", True)],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                port["name"]: {"x-agentforge-type": port.get("type", "any")}
                for port in node_outputs
            },
            "required": [port["name"] for port in node_outputs if port.get("required", True)],
        },
    }
    agent_id = data.get("agentId")
    if not agent_id:
        return config
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=409, detail=f"Agent for step {step.title} no longer exists")
    config.update(
        {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "kind": agent.kind.value,
            "purpose": agent.purpose,
            "draft_config": agent.draft_config or {},
            "input_schema": config["input_schema"] if node_inputs else (agent.input_schema or {}),
            "output_schema": config["output_schema"]
            if node_outputs
            else (agent.output_schema or {}),
        }
    )
    if executor in {"managed-ai", "crewai"}:
        provider = db.get(Provider, agent.provider_id) if agent.provider_id else None
        model = db.get(ModelCatalog, agent.model_catalog_id) if agent.model_catalog_id else None
        if not provider or not model:
            raise HTTPException(
                status_code=409, detail=f"AI provider/model missing for {agent.name}"
            )
        secret = db.scalar(select(ProviderSecret).where(ProviderSecret.provider_id == provider.id))
        config["provider"] = {
            "kind": provider.kind,
            "base_url": provider.base_url,
            "api_key": decrypt_secret(secret.encrypted_value) if secret else None,
            "model": model.model_id,
        }
    elif executor == "mcp":
        server = db.get(McpServer, agent.mcp_server_id) if agent.mcp_server_id else None
        if not server:
            raise HTTPException(status_code=409, detail=f"MCP server missing for {agent.name}")
        if server.status == "disabled":
            raise HTTPException(status_code=409, detail=f"MCP server {server.name} is disabled")
        secret = db.scalar(
            select(McpServerSecret).where(McpServerSecret.mcp_server_id == server.id)
        )
        secret_payload = {}
        if secret:
            try:
                import json

                secret_payload = json.loads(decrypt_secret(secret.encrypted_value))
                if not isinstance(secret_payload, dict):
                    raise ValueError("Secret payload must be an object")
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=500, detail=f"MCP secret for {server.name} is invalid"
                )
        config["mcp"] = {
            "server_id": server.id,
            "server_name": server.name,
            "transport": server.transport,
            "endpoint": server.endpoint,
            "command": server.command,
            "headers": secret_payload.get("headers") or {},
            "environment": secret_payload.get("environment") or {},
            "tool_name": agent.mcp_tool_name,
            "protocol_version": server.protocol_version or "2025-11-25",
        }
    return config


@worker_router.post(
    "/jobs/claim",
    response_model=WorkerJobOut,
    responses={204: {"description": "No compatible job"}},
)
def claim_job(db: Session = Depends(get_db), worker: Worker = Depends(authenticated_worker)):
    now = utcnow()
    worker.last_seen_at = now
    worker.status = WorkerStatus.online
    expired = list(
        db.scalars(
            select(WorkerJob).where(
                WorkerJob.status == JobStatus.leased, WorkerJob.lease_expires_at < now
            )
        )
    )
    for job in expired:
        job.status = JobStatus.queued
        job.worker_id = None
        job.lease_hash = None
        job.lease_expires_at = None
    candidate_query = (
        select(WorkerJob)
        .where(WorkerJob.status == JobStatus.queued, WorkerJob.executor.in_(worker.executors))
        .order_by(WorkerJob.created_at)
        .limit(50)
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        candidate_query = candidate_query.with_for_update(skip_locked=True)
    candidates = list(db.scalars(candidate_query))
    if worker.worker_class in {"gpu", "universal"}:
        candidates.sort(key=lambda job: (job.required_worker_class != "gpu", job.created_at))
    chosen = None
    chosen_step = None
    chosen_run = None
    for job in candidates:
        if job.required_worker_class == "gpu" and worker.worker_class not in {"gpu", "universal"}:
            continue
        step = db.get(StepRun, job.step_run_id)
        run = db.get(PipelineRun, job.run_id)
        if (
            not step
            or not run
            or run.status in {RunStatus.failed, RunStatus.cancelled, RunStatus.succeeded}
        ):
            continue
        if _step_is_ready(db, run, step):
            chosen, chosen_step, chosen_run = job, step, run
            break
    if not chosen or not chosen_step or not chosen_run:
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        mapped_input = (
            dict(chosen_step.input_payload or {})
            if chosen_run.engine == "langgraph"
            else _step_input(db, chosen_run, chosen_step)
        )
    except ValueError as exc:
        message = str(exc)
        chosen.status = JobStatus.failed
        chosen.error_message = message
        chosen.finished_at = now
        chosen_step.status = RunStatus.failed
        chosen_step.current_action = message[:300]
        chosen_step.finished_at = now
        chosen_run.status = RunStatus.failed
        chosen_run.finished_at = now
        db.add(
            RunEvent(
                run_id=chosen_run.id,
                step_run_id=chosen_step.id,
                kind="mapping.failed",
                level="error",
                title="Mapovanie vstupu zlyhalo",
                message=message,
                payload={},
            )
        )
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        config = _job_config(db, chosen_run, chosen_step, chosen.executor)
    except HTTPException as exc:
        message = str(exc.detail)
        chosen.status = JobStatus.failed
        chosen.error_message = message
        chosen.finished_at = now
        chosen_step.status = RunStatus.failed
        chosen_step.current_action = message[:300]
        chosen_step.finished_at = now
        chosen_run.status = RunStatus.failed
        chosen_run.finished_at = now
        db.add(
            RunEvent(
                run_id=chosen_run.id,
                step_run_id=chosen_step.id,
                kind="job.configuration.failed",
                level="error",
                title="Konfigurácia kroku zlyhala",
                message=message,
                payload={"executor": chosen.executor},
            )
        )
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    lease = create_opaque_token("lease")
    lease_result = db.execute(
        update(WorkerJob)
        .where(WorkerJob.id == chosen.id, WorkerJob.status == JobStatus.queued)
        .values(
            status=JobStatus.leased,
            worker_id=worker.id,
            lease_hash=hash_token(lease),
            lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
            attempts=WorkerJob.attempts + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if lease_result.rowcount != 1:
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    db.refresh(chosen)
    chosen_step.status = RunStatus.running
    chosen_step.progress = 10
    chosen_step.started_at = chosen_step.started_at or now
    chosen_step.current_action = f"Vykonáva worker {worker.name}"
    chosen_step.input_payload = mapped_input
    chosen_run.status = RunStatus.running
    chosen_run.started_at = chosen_run.started_at or now
    db.add(
        RunEvent(
            run_id=chosen_run.id,
            step_run_id=chosen_step.id,
            kind="worker.claimed",
            title="Worker prevzal krok",
            message=worker.name,
            payload={"worker_id": worker.id, "executor": chosen.executor},
        )
    )
    db.add(
        RunEvent(
            run_id=chosen_run.id,
            step_run_id=chosen_step.id,
            kind="mapping.applied",
            title="Vstupy namapované podľa názvov portov",
            message=", ".join(mapped_input) or "Bez dátových vstupov",
            payload={"input": mapped_input},
        )
    )
    db.commit()
    return WorkerJobOut(
        id=chosen.id,
        lease_token=lease,
        executor=chosen.executor,
        required_worker_class=chosen.required_worker_class,
        run_id=chosen.run_id,
        step_run_id=chosen.step_run_id,
        input_payload=chosen_step.input_payload,
        config=config,
    )


def _leased_job(job_id: str, lease_token: str, worker: Worker, db: Session) -> WorkerJob:
    job = db.get(WorkerJob, job_id)
    if (
        not job
        or job.worker_id != worker.id
        or job.status != JobStatus.leased
        or job.lease_hash != hash_token(lease_token)
    ):
        raise HTTPException(status_code=409, detail="Job lease is not valid")
    if not job.lease_expires_at or as_aware(job.lease_expires_at) < utcnow():
        raise HTTPException(status_code=409, detail="Job lease expired")
    return job


def _cancelled_job_for_worker(job_id: str, worker: Worker, db: Session) -> bool:
    """Acknowledge late worker calls after a user cancelled the run."""
    job = db.get(WorkerJob, job_id)
    if not job or job.worker_id != worker.id:
        return False
    run = db.get(PipelineRun, job.run_id)
    return bool(run and run.status == RunStatus.cancelled)


def _normalize_named_output(run: PipelineRun, step: StepRun, output: dict) -> dict:
    node = next(
        (
            item
            for item in (run.graph_snapshot or {}).get("nodes", [])
            if item.get("id") == step.node_id
        ),
        {},
    )
    expected = [
        port.get("name") for port in (node.get("data") or {}).get("outputs", []) if port.get("name")
    ]
    if not expected:
        return output
    if all(name in output for name in expected):
        return {name: output[name] for name in expected}
    nested = output.get("result")
    if isinstance(nested, dict) and all(name in nested for name in expected):
        return {name: nested[name] for name in expected}
    if len(expected) == 1 and "result" in output:
        return {expected[0]: output["result"]}
    missing = [name for name in expected if name not in output]
    raise ValueError(
        "Výstup nerešpektuje pomenovaný kontrakt. Chýbajú kľúče: " + ", ".join(missing)
    )


@worker_router.post("/jobs/{job_id}/events", status_code=204)
def job_event(
    job_id: str,
    payload: WorkerJobEvent,
    lease_token: Annotated[str, Header(alias="X-Lease-Token")],
    db: Session = Depends(get_db),
    worker: Worker = Depends(authenticated_worker),
) -> None:
    if _cancelled_job_for_worker(job_id, worker, db):
        return
    job = _leased_job(job_id, lease_token, worker, db)
    job.lease_expires_at = utcnow() + timedelta(seconds=LEASE_SECONDS)
    step = db.get(StepRun, job.step_run_id)
    db.add(
        RunEvent(
            run_id=job.run_id,
            step_run_id=job.step_run_id,
            kind="worker.log",
            level=payload.level,
            title="Worker log",
            message=payload.message,
            payload={"worker_id": worker.id},
        )
    )
    if step:
        step.current_action = payload.message[:300]
        if payload.level != "debug":
            step.progress = max(step.progress, 50)
    worker.last_seen_at = utcnow()
    worker.status = WorkerStatus.online
    db.commit()


@worker_router.post("/jobs/{job_id}/complete", status_code=204)
def complete_job(
    job_id: str,
    payload: WorkerJobComplete,
    db: Session = Depends(get_db),
    worker: Worker = Depends(authenticated_worker),
) -> None:
    if _cancelled_job_for_worker(job_id, worker, db):
        return
    job = _leased_job(job_id, payload.lease_token, worker, db)
    now = utcnow()
    worker.last_seen_at = now
    worker.status = WorkerStatus.online
    step = db.get(StepRun, job.step_run_id)
    run_query = select(PipelineRun).where(PipelineRun.id == job.run_id)
    if db.bind and db.bind.dialect.name == "postgresql":
        run_query = run_query.with_for_update()
    run = db.scalar(run_query)
    if not step or not run:
        raise HTTPException(status_code=409, detail="Run or step disappeared")
    job.finished_at = now
    job.lease_expires_at = None
    success = payload.success
    error = payload.error
    normalized_output = payload.output_payload
    mcp_server = None
    if job.executor == "mcp":
        node = next(
            (
                item
                for item in (run.graph_snapshot or {}).get("nodes", [])
                if item.get("id") == step.node_id
            ),
            {},
        )
        agent = db.get(Agent, (node.get("data") or {}).get("agentId"))
        mcp_server = (
            db.get(McpServer, agent.mcp_server_id) if agent and agent.mcp_server_id else None
        )
    if success:
        try:
            normalized_output = _normalize_named_output(run, step, payload.output_payload)
        except ValueError as exc:
            success = False
            error = str(exc)
    if success:
        job.status = JobStatus.succeeded
        step.status = RunStatus.succeeded
        step.progress = 100
        step.current_action = "Dokončené"
        step.output_payload = normalized_output
        step.finished_at = now
        db.add(
            RunEvent(
                run_id=run.id,
                step_run_id=step.id,
                kind="step.succeeded",
                title="Krok dokončený",
                message=worker.name,
                payload={"output": normalized_output},
            )
        )
        if mcp_server:
            mcp_server.status = "online"
            mcp_server.status_message = f"Last call succeeded on worker {worker.name}"
            mcp_server.last_checked_at = now
            db.add(
                RunEvent(
                    run_id=run.id,
                    step_run_id=step.id,
                    kind="mcp.call.succeeded",
                    title="MCP tool dokončený",
                    message=mcp_server.name,
                    payload={"server_id": mcp_server.id},
                )
            )
        if run.engine == "langgraph":
            try:
                advance_langgraph_run(db, run, step)
            except Exception as exc:
                job.status = JobStatus.failed
                job.error_message = f"LangGraph transition failed: {exc}"
                step.status = RunStatus.failed
                step.current_action = job.error_message[:300]
                run.status = RunStatus.failed
                run.finished_at = now
                db.add(
                    RunEvent(
                        run_id=run.id,
                        step_run_id=step.id,
                        kind="langgraph.failed",
                        level="error",
                        title="LangGraph prechod zlyhal",
                        message=str(exc),
                        payload={},
                    )
                )
        else:
            remaining = db.scalar(
                select(WorkerJob)
                .where(
                    WorkerJob.run_id == run.id,
                    WorkerJob.status.in_([JobStatus.queued, JobStatus.leased]),
                )
                .limit(1)
            )
            if not remaining and run.status in {RunStatus.queued, RunStatus.running}:
                run.status = RunStatus.succeeded
                run.finished_at = now
        if run.status == RunStatus.succeeded:
            run.finished_at = now
    else:
        job.status = JobStatus.failed
        job.error_message = error
        step.status = RunStatus.failed
        step.current_action = error[:300] or "Worker zlyhal"
        step.finished_at = now
        run.status = RunStatus.failed
        run.finished_at = now
        if mcp_server:
            if error.startswith("MCP_TOOL_ERROR:"):
                mcp_server.status = "online"
                mcp_server.status_message = (
                    "Service reachable; last tool call returned an execution error"
                )
            elif error.startswith("MCP_CONTRACT_ERROR:"):
                mcp_server.status_message = (
                    "Last call was rejected by the agent input/output contract"
                )
            else:
                mcp_server.status = "error"
                mcp_server.status_message = error[:1000] or "MCP call failed"
            mcp_server.last_checked_at = now
            db.add(
                RunEvent(
                    run_id=run.id,
                    step_run_id=step.id,
                    kind="mcp.call.failed",
                    level="error",
                    title="MCP volanie zlyhalo",
                    message=error,
                    payload={"server_id": mcp_server.id},
                )
            )
        queued_jobs = list(
            db.scalars(
                select(WorkerJob).where(
                    WorkerJob.run_id == run.id,
                    WorkerJob.status == JobStatus.queued,
                )
            )
        )
        for queued_job in queued_jobs:
            queued_job.status = JobStatus.failed
            queued_job.error_message = f"Upstream step '{step.title}' failed"
            queued_job.finished_at = now
            blocked_step = db.get(StepRun, queued_job.step_run_id)
            if blocked_step and blocked_step.status == RunStatus.queued:
                blocked_step.status = RunStatus.cancelled
                blocked_step.current_action = f"Nevykonané: zlyhal krok {step.title}"
                blocked_step.finished_at = now
        db.add(
            RunEvent(
                run_id=run.id,
                step_run_id=step.id,
                kind="step.failed",
                level="error",
                title="Krok zlyhal",
                message=error,
                payload={"worker_id": worker.id},
            )
        )
    db.commit()


@worker_router.get("/download", response_class=FileResponse, include_in_schema=False)
def download_worker() -> FileResponse:
    from pathlib import Path

    return FileResponse(
        Path(__file__).resolve().parents[1] / "static" / "agent-forge-worker",
        filename="agent-forge-worker",
        media_type="text/x-python",
    )


@worker_router.get("/install.sh", response_class=PlainTextResponse, include_in_schema=False)
def install_script() -> str:
    return """#!/bin/sh
set -eu
base=${AGENT_FORGE_URL:?Set AGENT_FORGE_URL, for example https://forge.example.com}
dest=${HOME}/.local/bin/agent-forge-worker
mkdir -p "$(dirname "$dest")"
curl -fsSL "${base%/}/api/v1/worker/download" -o "$dest"
chmod 0755 "$dest"
echo "Installed $dest"
"""
