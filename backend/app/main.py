from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from .config import get_settings
from .database import Base, engine
from .routers import admin, agents, audit, auth, mcp_servers, pipelines, providers, runs, workers


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(pipelines.router, prefix="/api/v1")
app.include_router(runs.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(providers.router, prefix="/api/v1")
app.include_router(mcp_servers.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(workers.admin_router, prefix="/api/v1")
app.include_router(workers.worker_router, prefix="/api/v1")


@app.on_event("startup")
def create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    worker_columns = {column["name"] for column in inspect(engine).get_columns("workers")}
    agent_columns = {column["name"] for column in inspect(engine).get_columns("agents")}
    job_columns = {column["name"] for column in inspect(engine).get_columns("worker_jobs")}
    pipeline_columns = {column["name"] for column in inspect(engine).get_columns("pipelines")}
    run_columns = {column["name"] for column in inspect(engine).get_columns("pipeline_runs")}
    if "worker_class" not in worker_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE workers ADD COLUMN worker_class VARCHAR(20) NOT NULL DEFAULT 'universal'"
                )
            )
    if "execution_requirement" not in agent_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE agents ADD COLUMN execution_requirement VARCHAR(20) NOT NULL DEFAULT 'cpu'"
                )
            )
    if "required_worker_class" not in job_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE worker_jobs ADD COLUMN required_worker_class VARCHAR(20) NOT NULL DEFAULT 'cpu'"
                )
            )
    if "mcp_server_id" not in agent_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE agents ADD COLUMN mcp_server_id VARCHAR(36)"))
            connection.execute(text("ALTER TABLE agents ADD COLUMN mcp_tool_name VARCHAR(128)"))
    if "engine" not in pipeline_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE pipelines ADD COLUMN engine VARCHAR(30) NOT NULL DEFAULT 'legacy'"
                )
            )
    if "engine" not in run_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE pipeline_runs ADD COLUMN engine VARCHAR(30) NOT NULL DEFAULT 'legacy'"
                )
            )
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("ALTER TYPE agentkind ADD VALUE IF NOT EXISTS 'mcp'"))
            connection.execute(text("ALTER TYPE agentkind ADD VALUE IF NOT EXISTS 'crewai'"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
