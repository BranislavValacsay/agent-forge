"""Worker execution contracts shared by all orchestration engines.

LangGraph decides *when* a node is ready. This module decides *where* and *how*
the node is executed. Keeping the concerns separate lets CrewAI runtimes,
OCI image builds and Helm deployments plug in without changing graph semantics.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .models import Agent


@dataclass(frozen=True)
class ExecutionSpec:
    executor: str
    required_worker_class: str


def execution_spec_for_node(db: Session, node: dict) -> ExecutionSpec:
    data = node.get("data") or {}
    if data.get("nodeKind", "agent") != "agent":
        return ExecutionSpec(executor="builtin", required_worker_class="cpu")

    agent = db.get(Agent, data.get("agentId")) if data.get("agentId") else None
    required_worker_class = agent.execution_requirement if agent else "cpu"
    mode = (agent.draft_config or {}).get("deployment_mode") if agent else None
    if mode == "custom-image":
        executor = "podman"
    elif agent and agent.kind.value == "mcp":
        executor = "mcp"
    elif agent and agent.kind.value == "ai":
        executor = "managed-ai"
    elif agent and agent.kind.value == "crewai":
        executor = "crewai"
    else:
        executor = "process"
    return ExecutionSpec(executor=executor, required_worker_class=required_worker_class)
