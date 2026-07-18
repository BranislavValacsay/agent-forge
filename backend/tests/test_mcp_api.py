import asyncio
import importlib.machinery
import importlib.util
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import User
from app.routers.mcp_servers import discover_http
from app.security import hash_password


class FakeMcpHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def do_POST(self) -> None:
        if self.headers.get("Authorization") != "Bearer test-token":
            self.send_response(401)
            self.end_headers()
            return
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        method = payload.get("method")
        if method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        if method == "initialize":
            result = {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "fake-http", "version": "1.0"},
            }
        elif method == "tools/list":
            result = {"tools": [{"name": "echo", "description": "Echo", "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}}, "outputSchema": {"type": "object", "properties": {"answer": {"type": "string"}}}}]}
        elif method == "tools/call":
            result = {"content": [{"type": "text", "text": "ok"}], "structuredContent": {"answer": payload.get("params", {}).get("arguments", {}).get("value")}, "isError": False}
        else:
            result = {}
        body = json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if method == "initialize":
            self.send_header("MCP-Session-Id", "test-session")
        self.end_headers()
        self.wfile.write(body)


def test_streamable_http_discovery() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMcpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = asyncio.run(discover_http(f"http://127.0.0.1:{server.server_port}/mcp", {"Authorization": "Bearer test-token"}))
        assert result.ok is True
        assert result.protocol_version == "2025-11-25"
        assert result.server_info["name"] == "fake-http"
        assert [tool["name"] for tool in result.tools] == ["echo"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_streamable_http_worker_call(monkeypatch) -> None:
    path = Path(__file__).parents[1] / "app" / "static" / "agent-forge-worker"
    loader = importlib.machinery.SourceFileLoader("agent_forge_mcp_http_worker", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    worker = importlib.util.module_from_spec(spec)
    loader.exec_module(worker)
    monkeypatch.setattr(worker, "emit", lambda *_args, **_kwargs: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMcpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        job = {
            "id": "http-mcp-job",
            "input_payload": {"value": "from HTTP"},
            "config": {
                "draft_config": {"timeout_seconds": 10},
                "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
                "output_schema": {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]},
                "mcp": {"transport": "streamable-http", "endpoint": f"http://127.0.0.1:{server.server_port}/mcp", "headers": {"Authorization": "Bearer test-token"}, "tool_name": "echo", "server_name": "fake-http"},
            },
        }
        assert worker.run_mcp({}, job) == {"answer": "from HTTP"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_stdio_mcp_server_and_agent_crud() -> None:
    password = "a-long-mcp-test-password"
    email = f"mcp-root-{uuid.uuid4()}@example.com"
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email=email, display_name="MCP Root", password_hash=hash_password(password), is_root=True))
            db.commit()
        assert client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200
        server_response = client.post("/api/v1/mcp-servers", json={
            "name": "Test stdio MCP",
            "slug": f"test-mcp-{uuid.uuid4().hex[:8]}",
            "description": "test",
            "transport": "stdio",
            "endpoint": None,
            "command": ["python3", "fake-server.py"],
            "visibility": "private",
            "secret_headers": {},
            "secret_environment": {"TOKEN": "secret-value"},
        })
        assert server_response.status_code == 201
        server = server_response.json()
        assert server["status"] == "unknown"
        assert server["has_secret"] is True
        assert "secret-value" not in str(server)
        assert client.post(f"/api/v1/mcp-servers/{server['id']}/connect").status_code == 422

        other_password = "another-long-test-password"
        other_email = f"mcp-user-{uuid.uuid4()}@example.com"
        with SessionLocal() as db:
            db.add(User(email=other_email, display_name="MCP User", password_hash=hash_password(other_password), is_root=False))
            db.commit()
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.post("/api/v1/auth/login", json={"email": other_email, "password": other_password}).status_code == 200
        forbidden_agent = client.post("/api/v1/agents", json={
            "name": "Forbidden MCP",
            "slug": f"forbidden-mcp-{uuid.uuid4().hex[:8]}",
            "kind": "mcp",
            "execution_requirement": "cpu",
            "visibility": "private",
            "mcp_server_id": server["id"],
            "mcp_tool_name": "echo",
            "draft_config": {},
            "input_schema": {},
            "output_schema": {},
        })
        assert forbidden_agent.status_code == 404
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200

        agent_response = client.post("/api/v1/agents", json={
            "name": "MCP echo",
            "slug": f"mcp-echo-{uuid.uuid4().hex[:8]}",
            "description": "test",
            "purpose": "call echo",
            "kind": "mcp",
            "execution_requirement": "cpu",
            "visibility": "private",
            "mcp_server_id": server["id"],
            "mcp_tool_name": "echo",
            "draft_config": {"deployment_mode": "mcp", "timeout_seconds": 10},
            "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
            "output_schema": {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]},
        })
        assert agent_response.status_code == 201
        agent = agent_response.json()
        assert agent["kind"] == "mcp"
        assert agent["mcp_server_id"] == server["id"]
        assert agent["mcp_tool_name"] == "echo"
        assert client.delete(f"/api/v1/mcp-servers/{server['id']}").status_code == 409

        registration_token = client.post("/api/v1/workers/registration-tokens", json={"name_hint": "mcp-worker", "expires_in_minutes": 30}).json()["token"]
        registration = client.post("/api/v1/worker/register", json={
            "registration_token": registration_token,
            "name": "mcp-worker",
            "worker_class": "cpu",
            "executors": ["mcp"],
            "version": "0.5.0",
            "platform": "linux",
            "architecture": "x86_64",
        }).json()
        worker_headers = {"Authorization": f"Bearer {registration['worker_token']}"}
        graph = {"nodes": [{"id": "mcp", "position": {"x": 0, "y": 0}, "data": {"label": "MCP echo", "nodeKind": "agent", "agentId": agent["id"], "agentName": agent["name"], "inputs": [{"name": "value", "type": "string", "required": False}], "outputs": [{"name": "answer", "type": "string"}]}}], "edges": []}
        pipeline = client.post("/api/v1/pipelines", json={"name": "MCP failure", "slug": f"mcp-failure-{uuid.uuid4().hex[:8]}", "description": "", "visibility": "private", "graph": graph, "input_schema": {}}).json()
        run = client.post(f"/api/v1/pipelines/{pipeline['id']}/runs", json={"trigger_kind": "manual", "input_payload": {"value": "hello"}}).json()
        claim = client.post("/api/v1/worker/jobs/claim", json={}, headers=worker_headers)
        assert claim.status_code == 200
        assert claim.json()["executor"] == "mcp"
        assert claim.json()["config"]["mcp"]["tool_name"] == "echo"
        assert claim.json()["config"]["mcp"]["environment"]["TOKEN"] == "secret-value"
        assert client.post(
            f"/api/v1/worker/jobs/{claim.json()['id']}/complete",
            json={"lease_token": claim.json()["lease_token"], "success": False, "output_payload": {}, "error": "MCP_TRANSPORT_ERROR: connection refused"},
            headers=worker_headers,
        ).status_code == 204
        assert client.get(f"/api/v1/runs/{run['id']}").json()["status"] == "failed"
        current_server = next(item for item in client.get("/api/v1/mcp-servers").json() if item["id"] == server["id"])
        assert current_server["status"] == "error"
        assert "connection refused" in current_server["status_message"]
        assert client.delete(f"/api/v1/pipelines/{pipeline['id']}").status_code == 204
        assert client.delete(f"/api/v1/agents/{agent['id']}").status_code == 204
        assert client.delete(f"/api/v1/mcp-servers/{server['id']}").status_code == 204
