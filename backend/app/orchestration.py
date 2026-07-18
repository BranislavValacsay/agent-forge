"""Durable orchestration engines for Agent Forge pipeline runs."""

import operator
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .contracts import assign_at, edge_mapping, value_at
from .execution import execution_spec_for_node
from .models import JobStatus, PipelineRun, RunEvent, RunStatus, StepRun, WorkerJob


class PipelineState(TypedDict):
    # Each node owns one key, therefore parallel branches merge without overwrites.
    outputs: Annotated[dict[str, dict[str, Any]], operator.or_]


def _node_map(graph: dict) -> dict[str, dict]:
    return {str(node.get("id")): node for node in graph.get("nodes", []) if node.get("id")}


def _predecessors(graph: dict) -> dict[str, set[str]]:
    nodes = _node_map(graph)
    result = {node_id: set() for node_id in nodes}
    for edge in graph.get("edges", []):
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source in nodes and target in nodes:
            result[target].add(source)
    return result


def _mapped_input(graph: dict, node_id: str, outputs: dict, initial_input: dict) -> dict:
    data_edges = [
        edge
        for edge in graph.get("edges", [])
        if str(edge.get("target")) == node_id and (edge.get("data") or {}).get("kind") != "control"
    ]
    if not data_edges:
        return deepcopy(initial_input)
    result: dict[str, Any] = {}
    assigned: set[str] = set()
    for edge in data_edges:
        mapping = edge_mapping(edge)
        if not mapping:
            continue
        target = mapping.get("target")
        source_id = str(edge.get("source"))
        if not isinstance(target, str) or not target:
            raise ValueError("Dátové spojenie nemá cieľový názov vstupu")
        if target in assigned:
            raise ValueError(f"Viac vetiev zapisuje do rovnakého vstupu '{target}'")
        try:
            assign_at(result, target, deepcopy(value_at(outputs[source_id], mapping["source"])))
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Mapovanie {mapping.get('source')} → {target} zlyhalo: {exc}") from exc
        assigned.add(target)
    return result


def _build_graph(run: PipelineRun, checkpointer):
    graph = run.graph_snapshot or {"nodes": [], "edges": []}
    nodes = _node_map(graph)
    predecessors = _predecessors(graph)
    builder = StateGraph(PipelineState)
    # LangGraph reserves namespace separators such as ':', so external node IDs
    # stay in interrupt payloads while internal graph names are deterministic.
    langgraph_names = {node_id: f"af_node_{index}" for index, node_id in enumerate(nodes)}

    for node_id in nodes:
        def execute(state: PipelineState, current_node_id: str = node_id):
            node_input = _mapped_input(graph, current_node_id, state.get("outputs", {}), run.input_payload or {})
            output = interrupt({"node_id": current_node_id, "input_payload": node_input})
            if not isinstance(output, dict):
                raise ValueError(f"Node {current_node_id} returned a non-object output")
            return {"outputs": {current_node_id: output}}

        builder.add_node(langgraph_names[node_id], execute)

    for node_id, sources in predecessors.items():
        target = langgraph_names[node_id]
        if not sources:
            builder.add_edge(START, target)
        elif len(sources) == 1:
            builder.add_edge(langgraph_names[next(iter(sources))], target)
        else:
            builder.add_edge([langgraph_names[source] for source in sorted(sources)], target)

    outgoing = {node_id: set() for node_id in nodes}
    for target, sources in predecessors.items():
        for source in sources:
            outgoing[source].add(target)
    for node_id, targets in outgoing.items():
        if not targets:
            builder.add_edge(langgraph_names[node_id], END)
    return builder.compile(checkpointer=checkpointer, name=f"agent-forge-run-{run.id}")


def _sqlite_checkpoint_path(database_url: str) -> str:
    raw = database_url.removeprefix("sqlite:///")
    if raw == ":memory:":
        return f"/tmp/agent_forge_langgraph_{id(database_url)}.sqlite"
    path = Path(raw)
    return str(path.with_name(f"{path.stem}_langgraph{path.suffix or '.db'}"))


@contextmanager
def checkpoint_saver() -> Iterator[Any]:
    settings = get_settings()
    url = settings.langgraph_checkpoint_url or settings.database_url
    if url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver

        connection_url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        with PostgresSaver.from_conn_string(connection_url) as saver:
            saver.setup()
            yield saver
        return

    from langgraph.checkpoint.sqlite import SqliteSaver

    path = _sqlite_checkpoint_path(url)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(path) as saver:
        saver.setup()
        yield saver


def _config(run: PipelineRun) -> dict:
    return {"configurable": {"thread_id": run.id}}


def _current_interrupts(compiled, config: dict) -> list:
    return [item for task in compiled.get_state(config).tasks for item in task.interrupts]


def _ensure_frontier_jobs(db: Session, run: PipelineRun, compiled, config: dict) -> bool:
    snapshot = compiled.get_state(config)
    outputs = snapshot.values.get("outputs", {}) if snapshot.values else {}
    nodes = _node_map(run.graph_snapshot or {})
    steps = {step.node_id: step for step in run.steps}
    created = False
    for current_interrupt in _current_interrupts(compiled, config):
        value = current_interrupt.value if isinstance(current_interrupt.value, dict) else {}
        node_id = str(value.get("node_id", ""))
        if not node_id or node_id in outputs:
            continue
        step = steps.get(node_id)
        node = nodes.get(node_id)
        if not step or not node:
            continue
        existing = db.scalar(select(WorkerJob).where(WorkerJob.step_run_id == step.id))
        if existing:
            continue
        spec = execution_spec_for_node(db, node)
        step.input_payload = value.get("input_payload") if isinstance(value.get("input_payload"), dict) else {}
        step.current_action = f"LangGraph: čaká na {spec.required_worker_class.upper()} worker ({spec.executor})"
        db.add(WorkerJob(run_id=run.id, step_run_id=step.id, executor=spec.executor, required_worker_class=spec.required_worker_class))
        db.add(RunEvent(run_id=run.id, step_run_id=step.id, kind="langgraph.node.ready", title="LangGraph aktivoval node", message=step.title, payload={"node_id": node_id, "input": step.input_payload}))
        created = True
    if not snapshot.next and all(step.status == RunStatus.succeeded for step in run.steps):
        run.status = RunStatus.succeeded
    return created


def start_langgraph_run(db: Session, run: PipelineRun) -> None:
    if not (run.graph_snapshot or {}).get("nodes"):
        run.status = RunStatus.succeeded
        return
    with checkpoint_saver() as saver:
        compiled = _build_graph(run, saver)
        config = _config(run)
        compiled.invoke({"outputs": {}}, config)
        _ensure_frontier_jobs(db, run, compiled, config)
    db.add(RunEvent(run_id=run.id, kind="langgraph.started", title="LangGraph engine spustený", message="Prvý frontier je pripravený", payload={"engine": "langgraph"}))


def advance_langgraph_run(db: Session, run: PipelineRun, completed_step: StepRun) -> None:
    with checkpoint_saver() as saver:
        compiled = _build_graph(run, saver)
        config = _config(run)
        snapshot = compiled.get_state(config)
        outputs = snapshot.values.get("outputs", {}) if snapshot.values else {}
        matching = next(
            (
                item
                for item in _current_interrupts(compiled, config)
                if isinstance(item.value, dict)
                and str(item.value.get("node_id")) == completed_step.node_id
                and completed_step.node_id not in outputs
            ),
            None,
        )
        if matching:
            compiled.invoke(Command(resume={matching.id: completed_step.output_payload}), config)
        _ensure_frontier_jobs(db, run, compiled, config)
        final_snapshot = compiled.get_state(config)
        if not final_snapshot.next and all(step.status == RunStatus.succeeded for step in run.steps):
            run.status = RunStatus.succeeded
    db.add(RunEvent(run_id=run.id, step_run_id=completed_step.id, kind="langgraph.advanced", title="LangGraph stav aktualizovaný", message=completed_step.title, payload={"node_id": completed_step.node_id}))
