import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AclEntry, Agent, McpServer, McpServerSecret, User
from ..schemas import McpConnectionResult, McpServerCreate, McpServerOut
from ..security import current_user, decrypt_secret, encrypt_secret, has_permission


router = APIRouter(prefix="/mcp-servers", tags=["mcp servers"])
PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOLS = {"2025-11-25", "2025-06-18", "2025-03-26"}
RESERVED_HEADERS = {"accept", "content-type", "host", "origin", "mcp-session-id", "mcp-protocol-version"}
MAX_DISCOVERY_RESPONSE_BYTES = 5 * 1024 * 1024


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def require_root(user: User) -> None:
    if not user.is_root:
        raise HTTPException(status_code=403, detail="Root access required")


def clean_endpoint(value: str | None) -> str:
    endpoint = (value or "").strip()
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="MCP endpoint must include http:// or https://")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Do not put credentials in the MCP URL; use secret headers")
    return endpoint


def validated_data(payload: McpServerCreate) -> dict:
    for name, value in payload.secret_headers.items():
        if name.lower() in RESERVED_HEADERS:
            raise HTTPException(status_code=422, detail=f"MCP secret header '{name}' is reserved")
        if not name or "\r" in name or "\n" in name or "\r" in value or "\n" in value:
            raise HTTPException(status_code=422, detail="MCP secret headers contain invalid characters")
    data = payload.model_dump(exclude={"secret_headers", "secret_environment"})
    if payload.transport == "streamable-http":
        data["endpoint"] = clean_endpoint(payload.endpoint)
        data["command"] = []
    else:
        command = [part for part in payload.command if part]
        if not command:
            raise HTTPException(status_code=422, detail="stdio MCP server requires a command argument array")
        if any("\x00" in part for part in command):
            raise HTTPException(status_code=422, detail="stdio command contains an invalid null byte")
        data["endpoint"] = None
        data["command"] = command
    return data


def server_secret(server_id: str, db: Session) -> tuple[dict[str, str], dict[str, str]]:
    secret = db.scalar(select(McpServerSecret).where(McpServerSecret.mcp_server_id == server_id))
    if not secret:
        return {}, {}
    try:
        payload = json.loads(decrypt_secret(secret.encrypted_value))
        return dict(payload.get("headers") or {}), dict(payload.get("environment") or {})
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Stored MCP secret cannot be decrypted") from exc


def public_server(server: McpServer, db: Session) -> dict:
    secret = db.scalar(select(McpServerSecret.id).where(McpServerSecret.mcp_server_id == server.id))
    return {
        "id": server.id,
        "name": server.name,
        "slug": server.slug,
        "description": server.description,
        "transport": server.transport,
        "endpoint": server.endpoint,
        "command": server.command,
        "visibility": server.visibility,
        "owner_id": server.owner_id,
        "status": server.status,
        "status_message": server.status_message,
        "protocol_version": server.protocol_version,
        "server_info": server.server_info,
        "capabilities": server.capabilities,
        "tools_snapshot": server.tools_snapshot,
        "has_secret": secret is not None,
        "last_checked_at": server.last_checked_at,
        "created_at": server.created_at,
        "updated_at": server.updated_at,
    }


def parse_mcp_response(response: httpx.Response, request_id: int) -> dict:
    if response.status_code == 202 and not response.content:
        return {}
    response.raise_for_status()
    if len(response.content) > MAX_DISCOVERY_RESPONSE_BYTES:
        raise RuntimeError("MCP discovery response exceeds the 5 MiB safety limit")
    content_type = response.headers.get("content-type", "").lower()
    if "text/event-stream" in content_type:
        messages = []
        for line in response.text.splitlines():
            if line.startswith("data:") and line[5:].strip():
                try:
                    messages.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    continue
        payload = next((item for item in messages if item.get("id") == request_id), None)
        if payload is None:
            raise RuntimeError("MCP SSE response did not contain the requested JSON-RPC response")
        return payload
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("MCP server returned neither JSON nor a valid SSE response") from exc


async def mcp_post(
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict,
    secret_headers: dict[str, str],
    session_id: str | None = None,
    protocol_version: str | None = None,
) -> tuple[dict, str | None]:
    headers = {
        **secret_headers,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["MCP-Session-Id"] = session_id
    if protocol_version:
        headers["MCP-Protocol-Version"] = protocol_version
    response = await client.post(endpoint, headers=headers, json=payload)
    request_id = payload.get("id", -1)
    parsed = parse_mcp_response(response, request_id)
    return parsed, response.headers.get("MCP-Session-Id") or session_id


def rpc_result(payload: dict, operation: str) -> dict:
    if payload.get("error"):
        error = payload["error"]
        raise RuntimeError(f"{operation}: {error.get('message', 'JSON-RPC error')} ({error.get('code', 'unknown')})")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"{operation}: MCP response has no result object")
    return result


async def discover_http(endpoint: str, secret_headers: dict[str, str]) -> McpConnectionResult:
    request_id = 1
    session_id = None
    protocol_version = PROTOCOL_VERSION
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=8), follow_redirects=False, trust_env=False) as client:
            initialized, session_id = await mcp_post(
                client,
                endpoint,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "agent-forge", "title": "Agent Forge", "version": "0.5.0"},
                    },
                },
                secret_headers,
            )
            init_result = rpc_result(initialized, "initialize")
            protocol_version = init_result.get("protocolVersion") or PROTOCOL_VERSION
            if protocol_version not in SUPPORTED_PROTOCOLS:
                raise RuntimeError(f"Server negotiated unsupported MCP protocol {protocol_version}")
            capabilities = init_result.get("capabilities") or {}
            if "tools" not in capabilities:
                raise RuntimeError("MCP server did not advertise the tools capability")
            await mcp_post(
                client,
                endpoint,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                secret_headers,
                session_id,
                protocol_version,
            )
            tools: list[dict] = []
            cursor = None
            while True:
                request_id += 1
                params = {"cursor": cursor} if cursor else {}
                listed, session_id = await mcp_post(
                    client,
                    endpoint,
                    {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": params},
                    secret_headers,
                    session_id,
                    protocol_version,
                )
                result = rpc_result(listed, "tools/list")
                tools.extend(item for item in result.get("tools", []) if isinstance(item, dict) and item.get("name"))
                cursor = result.get("nextCursor")
                if not cursor:
                    break
                if len(tools) > 5000:
                    raise RuntimeError("MCP tool catalog exceeds the 5000 tool safety limit")
            if session_id:
                try:
                    await client.delete(endpoint, headers={"MCP-Session-Id": session_id, "MCP-Protocol-Version": protocol_version, **secret_headers})
                except httpx.HTTPError:
                    pass
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"MCP connection failed: {exc}") from exc
    return McpConnectionResult(
        ok=True,
        message=f"Connected; discovered {len(tools)} tools",
        protocol_version=protocol_version,
        server_info=init_result.get("serverInfo") or {},
        capabilities=capabilities,
        tools=tools,
    )


@router.get("", response_model=list[McpServerOut])
def list_servers(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    servers = list(db.scalars(select(McpServer).order_by(McpServer.updated_at.desc())))
    return [
        public_server(server, db)
        for server in servers
        if has_permission(db, user, "mcp_server", server.id, server.owner_id, server.visibility, "view")
    ]


@router.post("", response_model=McpServerOut, status_code=201)
def create_server(payload: McpServerCreate, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    require_root(user)
    server = McpServer(**validated_data(payload), owner_id=user.id)
    db.add(server)
    db.flush()
    if payload.secret_headers or payload.secret_environment:
        secret_payload = {"headers": payload.secret_headers, "environment": payload.secret_environment}
        db.add(McpServerSecret(mcp_server_id=server.id, encrypted_value=encrypt_secret(json.dumps(secret_payload))))
    db.commit()
    db.refresh(server)
    return public_server(server, db)


@router.put("/{server_id}", response_model=McpServerOut)
def update_server(payload: McpServerCreate, server_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    require_root(user)
    server = db.get(McpServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    for key, value in validated_data(payload).items():
        setattr(server, key, value)
    if payload.secret_headers or payload.secret_environment:
        value = encrypt_secret(json.dumps({"headers": payload.secret_headers, "environment": payload.secret_environment}))
        secret = db.scalar(select(McpServerSecret).where(McpServerSecret.mcp_server_id == server.id))
        if secret:
            secret.encrypted_value = value
        else:
            db.add(McpServerSecret(mcp_server_id=server.id, encrypted_value=value))
    server.status = "unknown"
    server.status_message = "Configuration changed; synchronization required"
    db.commit()
    db.refresh(server)
    return public_server(server, db)


@router.post("/test", response_model=McpConnectionResult)
async def test_server(payload: McpServerCreate, user: User = Depends(current_user)) -> McpConnectionResult:
    require_root(user)
    if payload.transport != "streamable-http":
        raise HTTPException(status_code=422, detail="stdio servers are tested by the execution worker")
    return await discover_http(clean_endpoint(payload.endpoint), payload.secret_headers)


@router.post("/{server_id}/connect", response_model=McpConnectionResult)
async def connect_server(server_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> McpConnectionResult:
    require_root(user)
    server = db.get(McpServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if server.transport != "streamable-http":
        raise HTTPException(status_code=422, detail="stdio servers are discovered and tested by an MCP worker")
    headers, _ = server_secret(server.id, db)
    try:
        result = await discover_http(server.endpoint or "", headers)
    except HTTPException as exc:
        server.status = "error"
        server.status_message = str(exc.detail)[:1000]
        server.last_checked_at = utcnow()
        db.commit()
        raise
    server.status = "online"
    server.status_message = result.message
    server.protocol_version = result.protocol_version
    server.server_info = result.server_info
    server.capabilities = result.capabilities
    server.tools_snapshot = result.tools
    server.last_checked_at = utcnow()
    db.commit()
    return result


@router.post("/{server_id}/disable", response_model=McpServerOut)
def disable_server(server_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    require_root(user)
    server = db.get(McpServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    server.status = "disabled"
    server.status_message = "Disabled by administrator"
    db.commit()
    return public_server(server, db)


@router.post("/{server_id}/enable", response_model=McpServerOut)
def enable_server(server_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    require_root(user)
    server = db.get(McpServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    server.status = "unknown"
    server.status_message = "Enabled; connection not checked"
    db.commit()
    return public_server(server, db)


@router.delete("/{server_id}", status_code=204)
def delete_server(server_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> None:
    require_root(user)
    server = db.get(McpServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    agents = list(db.scalars(select(Agent.name).where(Agent.mcp_server_id == server.id)))
    if agents:
        raise HTTPException(status_code=409, detail=f"MCP server is used by agent(s): {', '.join(agents)}")
    db.execute(delete(McpServerSecret).where(McpServerSecret.mcp_server_id == server.id))
    db.execute(delete(AclEntry).where(AclEntry.resource_type == "mcp_server", AclEntry.resource_id == server.id))
    db.delete(server)
    db.commit()
