from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    AclEntry,
    Agent,
    AgentKind,
    AgentVersion,
    McpServer,
    ModelCatalog,
    Pipeline,
    Provider,
    User,
)
from ..schemas import AgentCreate, AgentOut
from ..security import current_user, has_permission


router = APIRouter(prefix="/agents", tags=["agents"])


def validate_crewai_config(payload: AgentCreate, db: Session) -> None:
    if not payload.provider_id or not payload.model_catalog_id:
        raise HTTPException(status_code=422, detail="CrewAI agent requires a provider and model")
    provider = db.get(Provider, payload.provider_id)
    model = db.get(ModelCatalog, payload.model_catalog_id)
    if not provider or not provider.enabled or not model or not model.enabled:
        raise HTTPException(status_code=422, detail="Selected CrewAI provider/model is unavailable")
    if model.provider_id != provider.id:
        raise HTTPException(
            status_code=422, detail="Selected model does not belong to the provider"
        )

    config = payload.draft_config or {}
    if config.get("process", "sequential") not in {"sequential", "hierarchical"}:
        raise HTTPException(
            status_code=422, detail="CrewAI process must be sequential or hierarchical"
        )
    members = config.get("members")
    tasks = config.get("tasks")
    if not isinstance(members, list) or not 1 <= len(members) <= 20:
        raise HTTPException(status_code=422, detail="CrewAI requires 1 to 20 members")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 50:
        raise HTTPException(status_code=422, detail="CrewAI requires 1 to 50 tasks")

    roles: set[str] = set()
    for member in members:
        if not isinstance(member, dict):
            raise HTTPException(status_code=422, detail="Every CrewAI member must be an object")
        role = str(member.get("role", "")).strip()
        goal = str(member.get("goal", "")).strip()
        backstory = str(member.get("backstory", "")).strip()
        if not role or not goal or not backstory:
            raise HTTPException(
                status_code=422, detail="CrewAI member requires role, goal and backstory"
            )
        if role in roles:
            raise HTTPException(status_code=422, detail=f"Duplicate CrewAI role: {role}")
        if max(len(role), len(goal), len(backstory)) > 4000:
            raise HTTPException(status_code=422, detail="CrewAI member field is too long")
        roles.add(role)

    task_names: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise HTTPException(status_code=422, detail="Every CrewAI task must be an object")
        name = str(task.get("name", "")).strip()
        description = str(task.get("description", "")).strip()
        expected = str(task.get("expected_output", "")).strip()
        role = str(task.get("agent_role", "")).strip()
        if not name or not description or not expected or not role:
            raise HTTPException(
                status_code=422,
                detail="CrewAI task requires name, description, expected output and member",
            )
        if role not in roles:
            raise HTTPException(
                status_code=422, detail=f"CrewAI task references unknown role: {role}"
            )
        if name in task_names:
            raise HTTPException(status_code=422, detail=f"Duplicate CrewAI task name: {name}")
        if max(len(name), len(description), len(expected)) > 8000:
            raise HTTPException(status_code=422, detail="CrewAI task field is too long")
        task_names.add(name)


def validate_agent_references(payload: AgentCreate, db: Session, user: User) -> None:
    if payload.kind == AgentKind.crewai:
        validate_crewai_config(payload, db)
    if payload.kind == AgentKind.mcp:
        if not payload.mcp_server_id or not payload.mcp_tool_name:
            raise HTTPException(
                status_code=422, detail="MCP agent requires an MCP server and tool name"
            )
        server = db.get(McpServer, payload.mcp_server_id)
        if not server:
            raise HTTPException(status_code=422, detail="Selected MCP server does not exist")
        if not has_permission(
            db, user, "mcp_server", server.id, server.owner_id, server.visibility, "run"
        ):
            raise HTTPException(status_code=404, detail="Selected MCP server not found")
        if server.status == "disabled":
            raise HTTPException(status_code=409, detail="Selected MCP server is disabled")
        discovered = {tool.get("name") for tool in (server.tools_snapshot or [])}
        if discovered and payload.mcp_tool_name not in discovered:
            raise HTTPException(
                status_code=422,
                detail="Selected MCP tool is not present in the synchronized catalog",
            )


@router.get("", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Agent]:
    agents = list(db.scalars(select(Agent).order_by(Agent.updated_at.desc())))
    return [
        agent
        for agent in agents
        if has_permission(db, user, "agent", agent.id, agent.owner_id, agent.visibility, "view")
    ]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Agent:
    validate_agent_references(payload, db, user)
    agent = Agent(**payload.model_dump(), owner_id=user.id)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(
    agent_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent or not has_permission(
        db, user, "agent", agent.id, agent.owner_id, agent.visibility, "view"
    ):
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(
    payload: AgentCreate,
    agent_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent or not has_permission(
        db, user, "agent", agent.id, agent.owner_id, agent.visibility, "edit"
    ):
        raise HTTPException(status_code=404, detail="Agent not found")
    validate_agent_references(payload, db, user)
    for key, value in payload.model_dump().items():
        setattr(agent, key, value)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_agent(
    agent_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    agent = db.get(Agent, agent_id)
    if not agent or not has_permission(
        db, user, "agent", agent.id, agent.owner_id, agent.visibility, "manage"
    ):
        raise HTTPException(status_code=404, detail="Agent not found")
    used_by = [
        pipeline.name
        for pipeline in db.scalars(select(Pipeline))
        if any(
            (node.get("data") or {}).get("agentId") == agent_id
            for node in (pipeline.graph or {}).get("nodes", [])
        )
    ]
    if used_by:
        raise HTTPException(
            status_code=409,
            detail=f"Agent is used by pipeline(s): {', '.join(used_by)}. Remove its nodes first.",
        )
    db.execute(delete(AgentVersion).where(AgentVersion.agent_id == agent_id))
    db.execute(
        delete(AclEntry).where(AclEntry.resource_type == "agent", AclEntry.resource_id == agent_id)
    )
    db.delete(agent)
    db.commit()
