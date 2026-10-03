from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import engine
from .migrations import require_current_schema, upgrade_schema
from .i18n import localize_detail
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


@app.exception_handler(StarletteHTTPException)
async def localized_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": localize_detail(exc.detail, request.headers.get("accept-language"))},
        headers=exc.headers,
    )


@app.on_event("startup")
def create_schema() -> None:
    if settings.auto_migrate:
        upgrade_schema(engine)
    else:
        require_current_schema(engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
