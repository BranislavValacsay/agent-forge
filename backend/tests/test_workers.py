import uuid

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import User, WorkerJob
from app.security import hash_password


def test_worker_registration_is_one_time_and_worker_heartbeats() -> None:
    password = "a-long-test-password"
    email = f"root-{uuid.uuid4()}@example.com"
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email=email, display_name="Worker Test Root", password_hash=hash_password(password), is_root=True))
            db.commit()
        assert client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200
        audit = client.post("/api/v1/audit-events", json={"kind": "test.toast", "level": "success", "message": "Tracked toast", "resource_type": "test", "resource_id": None, "payload": {}})
        assert audit.status_code == 201
        assert any(event["kind"] == "test.toast" for event in client.get("/api/v1/audit-events").json())
        token_response = client.post("/api/v1/workers/registration-tokens", json={"name_hint": "remote-linux", "expires_in_minutes": 30})
        assert token_response.status_code == 201
        registration_token = token_response.json()["token"]
        payload = {
            "registration_token": registration_token,
            "name": "remote-linux",
            "worker_class": "cpu",
            "executors": ["process", "builtin"],
            "version": "test",
            "platform": "linux",
            "architecture": "x86_64",
        }
        registration = client.post("/api/v1/worker/register", json=payload)
        assert registration.status_code == 201
        assert client.post("/api/v1/worker/register", json=payload).status_code == 401
        worker_token = registration.json()["worker_token"]
        heartbeat = client.post(
            "/api/v1/worker/heartbeat",
            json={"executors": ["process", "builtin"], "version": "test"},
            headers={"Authorization": f"Bearer {worker_token}"},
        )
        assert heartbeat.status_code == 204
        workers = client.get("/api/v1/workers")
        assert workers.status_code == 200
        assert any(worker["name"] == "remote-linux" and worker["status"] == "online" and worker["worker_class"] == "cpu" for worker in workers.json())
        worker_id = registration.json()["worker_id"]
        assert client.post(f"/api/v1/workers/{worker_id}/disable").status_code == 204
        assert client.post(
            "/api/v1/worker/heartbeat",
            json={"executors": ["process", "builtin"], "version": "test"},
            headers={"Authorization": f"Bearer {worker_token}"},
        ).status_code == 401
        assert client.post(f"/api/v1/workers/{worker_id}/enable").status_code == 204
        assert client.post(
            "/api/v1/worker/heartbeat",
            json={"executors": ["process", "builtin"], "version": "test"},
            headers={"Authorization": f"Bearer {worker_token}"},
        ).status_code == 204

        agent = client.post("/api/v1/agents", json={
            "name": "Echo process",
            "slug": f"echo-{uuid.uuid4().hex[:8]}",
            "description": "test",
            "purpose": "echo",
            "kind": "script",
            "visibility": "private",
            "draft_config": {"deployment_mode": "managed-script", "language": "python", "code": "# test"},
            "input_schema": {},
            "output_schema": {},
        }).json()
        graph = {"nodes": [{"id": "echo", "position": {"x": 0, "y": 0}, "data": {"label": "Echo", "nodeKind": "agent", "agentId": agent["id"], "agentName": agent["name"], "inputs": [], "outputs": []}}], "edges": []}
        pipeline = client.post("/api/v1/pipelines", json={
            "name": "Worker test",
            "slug": f"worker-test-{uuid.uuid4().hex[:8]}",
            "description": "",
            "visibility": "private",
            "graph": graph,
            "input_schema": {},
        }).json()
        run = client.post(f"/api/v1/pipelines/{pipeline['id']}/runs", json={"trigger_kind": "manual", "input_payload": {"message": "hello"}})
        assert run.status_code == 201
        run_id = run.json()["id"]
        claim = client.post("/api/v1/worker/jobs/claim", json={}, headers={"Authorization": f"Bearer {worker_token}"})
        assert claim.status_code == 200
        assert claim.json()["executor"] == "process"
        assert claim.json()["required_worker_class"] == "cpu"
        assert claim.json()["input_payload"] == {"message": "hello"}
        completed = client.post(
            f"/api/v1/worker/jobs/{claim.json()['id']}/complete",
            json={"lease_token": claim.json()["lease_token"], "success": True, "output_payload": {"result": "hello"}, "error": ""},
            headers={"Authorization": f"Bearer {worker_token}"},
        )
        assert completed.status_code == 204
        assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "succeeded"
        empty_claim = client.post("/api/v1/worker/jobs/claim", json={}, headers={"Authorization": f"Bearer {worker_token}"})
        assert empty_claim.status_code == 204
        assert empty_claim.content == b""

        dag_graph = {
            "nodes": [
                {"id": "source", "position": {"x": 0, "y": 0}, "data": {"label": "Source", "nodeKind": "agent", "agentId": agent["id"], "agentName": agent["name"], "inputs": [], "outputs": [{"name": "third", "type": "string"}, {"name": "fourth", "type": "string"}]}},
                {"id": "left", "position": {"x": 250, "y": -100}, "data": {"label": "Left", "nodeKind": "agent", "agentId": agent["id"], "agentName": agent["name"], "inputs": [{"name": "text", "type": "string", "required": True}], "outputs": [{"name": "result", "type": "string"}]}},
                {"id": "right", "position": {"x": 250, "y": 100}, "data": {"label": "Right", "nodeKind": "agent", "agentId": agent["id"], "agentName": agent["name"], "inputs": [{"name": "text", "type": "string", "required": True}, {"name": "context", "type": "string", "required": True}], "outputs": [{"name": "result", "type": "string"}]}},
                {"id": "join", "position": {"x": 500, "y": 0}, "data": {"label": "Join", "nodeKind": "output", "inputs": [{"name": "left", "type": "string", "required": True}, {"name": "right", "type": "string", "required": True}], "outputs": []}},
            ],
            "edges": [
                {"id": "source-left", "source": "source", "target": "left", "sourceHandle": "out:third", "targetHandle": "in:text", "data": {"kind": "value"}},
                {"id": "source-right", "source": "source", "target": "right", "sourceHandle": "out:third", "targetHandle": "in:text", "data": {"kind": "value"}},
                {"id": "source-context", "source": "source", "target": "right", "sourceHandle": "out:fourth", "targetHandle": "in:context", "data": {"kind": "value"}},
                {"id": "left-join", "source": "left", "target": "join", "sourceHandle": "out:result", "targetHandle": "in:left", "data": {"kind": "value"}},
                {"id": "right-join", "source": "right", "target": "join", "sourceHandle": "out:result", "targetHandle": "in:right", "data": {"kind": "value"}},
            ],
        }
        dag_pipeline_response = client.post("/api/v1/pipelines", json={"name": "Parallel DAG", "slug": f"parallel-{uuid.uuid4().hex[:8]}", "description": "", "visibility": "private", "graph": dag_graph, "input_schema": {}})
        assert dag_pipeline_response.status_code == 201
        dag_pipeline = dag_pipeline_response.json()
        dag_run = client.post(f"/api/v1/pipelines/{dag_pipeline['id']}/runs", json={"trigger_kind": "manual", "input_payload": {}}).json()
        assert dag_run["engine"] == "langgraph"
        with SessionLocal() as db:
            assert len(list(db.query(WorkerJob).filter(WorkerJob.run_id == dag_run["id"]))) == 1
        dag_steps = {step["node_id"]: step["id"] for step in dag_run["steps"]}
        source_claim = client.post("/api/v1/worker/jobs/claim", json={}, headers={"Authorization": f"Bearer {worker_token}"})
        assert source_claim.status_code == 200
        assert source_claim.json()["step_run_id"] == dag_steps["source"]
        assert client.post(
            f"/api/v1/worker/jobs/{source_claim.json()['id']}/complete",
            json={"lease_token": source_claim.json()["lease_token"], "success": True, "output_payload": {"third": "shared", "fourth": "private"}, "error": ""},
            headers={"Authorization": f"Bearer {worker_token}"},
        ).status_code == 204
        with SessionLocal() as db:
            assert len(list(db.query(WorkerJob).filter(WorkerJob.run_id == dag_run["id"]))) == 3
        branch_claims = [
            client.post("/api/v1/worker/jobs/claim", json={}, headers={"Authorization": f"Bearer {worker_token}"}),
            client.post("/api/v1/worker/jobs/claim", json={}, headers={"Authorization": f"Bearer {worker_token}"}),
        ]
        assert all(claim.status_code == 200 for claim in branch_claims)
        claimed_steps = {claim.json()["step_run_id"]: claim.json() for claim in branch_claims}
        assert set(claimed_steps) == {dag_steps["left"], dag_steps["right"]}
        assert claimed_steps[dag_steps["left"]]["input_payload"] == {"text": "shared"}
        assert claimed_steps[dag_steps["right"]]["input_payload"] == {"text": "shared", "context": "private"}
        left_claim = claimed_steps[dag_steps["left"]]
        right_claim = claimed_steps[dag_steps["right"]]
        assert client.post(
            f"/api/v1/worker/jobs/{left_claim['id']}/complete",
            json={"lease_token": left_claim["lease_token"], "success": True, "output_payload": {"result": "L"}, "error": ""},
            headers={"Authorization": f"Bearer {worker_token}"},
        ).status_code == 204
        with SessionLocal() as db:
            assert len(list(db.query(WorkerJob).filter(WorkerJob.run_id == dag_run["id"]))) == 3
        assert client.post("/api/v1/worker/jobs/claim", json={}, headers={"Authorization": f"Bearer {worker_token}"}).status_code == 204
        assert client.post(
            f"/api/v1/worker/jobs/{right_claim['id']}/complete",
            json={"lease_token": right_claim["lease_token"], "success": True, "output_payload": {"result": "R"}, "error": ""},
            headers={"Authorization": f"Bearer {worker_token}"},
        ).status_code == 204
        with SessionLocal() as db:
            assert len(list(db.query(WorkerJob).filter(WorkerJob.run_id == dag_run["id"]))) == 4
        join_claim = client.post("/api/v1/worker/jobs/claim", json={}, headers={"Authorization": f"Bearer {worker_token}"})
        assert join_claim.status_code == 200
        assert join_claim.json()["step_run_id"] == dag_steps["join"]
        assert join_claim.json()["input_payload"] == {"left": "L", "right": "R"}
        assert client.post(
            f"/api/v1/worker/jobs/{join_claim.json()['id']}/complete",
            json={"lease_token": join_claim.json()["lease_token"], "success": True, "output_payload": {}, "error": ""},
            headers={"Authorization": f"Bearer {worker_token}"},
        ).status_code == 204
        assert client.get(f"/api/v1/runs/{dag_run['id']}").json()["status"] == "succeeded"
        assert client.delete(f"/api/v1/pipelines/{dag_pipeline['id']}").status_code == 204

        gpu_agent = client.post("/api/v1/agents", json={
            "name": "GPU only",
            "slug": f"gpu-{uuid.uuid4().hex[:8]}",
            "description": "test",
            "purpose": "gpu test",
            "kind": "script",
            "execution_requirement": "gpu",
            "visibility": "private",
            "draft_config": {"deployment_mode": "managed-script", "language": "python", "code": "# test"},
            "input_schema": {},
            "output_schema": {},
        }).json()
        gpu_graph = {"nodes": [{"id": "gpu", "position": {"x": 0, "y": 0}, "data": {"label": "GPU", "nodeKind": "agent", "agentId": gpu_agent["id"], "agentName": gpu_agent["name"], "inputs": [], "outputs": []}}], "edges": []}
        gpu_pipeline = client.post("/api/v1/pipelines", json={"name": "GPU test", "slug": f"gpu-test-{uuid.uuid4().hex[:8]}", "description": "", "visibility": "private", "graph": gpu_graph, "input_schema": {}}).json()
        gpu_run = client.post(f"/api/v1/pipelines/{gpu_pipeline['id']}/runs", json={"trigger_kind": "manual", "input_payload": {}}).json()
        assert client.post("/api/v1/worker/jobs/claim", json={}, headers={"Authorization": f"Bearer {worker_token}"}).status_code == 204
        assert client.post(f"/api/v1/runs/{gpu_run['id']}/cancel").status_code == 200
        assert client.delete(f"/api/v1/pipelines/{gpu_pipeline['id']}").status_code == 204
        assert client.delete(f"/api/v1/agents/{gpu_agent['id']}").status_code == 204

        edited_agent = client.put(f"/api/v1/agents/{agent['id']}", json={
            "name": "Echo process edited",
            "slug": agent["slug"],
            "description": "edited",
            "purpose": "echo",
            "kind": "script",
            "visibility": "private",
            "draft_config": agent["draft_config"],
            "input_schema": {},
            "output_schema": {},
        })
        assert edited_agent.status_code == 200
        assert edited_agent.json()["name"] == "Echo process edited"

        renamed = client.put(f"/api/v1/pipelines/{pipeline['id']}", json={
            "name": "Worker test renamed",
            "slug": pipeline["slug"],
            "description": pipeline["description"],
            "visibility": pipeline["visibility"],
            "graph": pipeline["graph"],
            "input_schema": pipeline["input_schema"],
        })
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Worker test renamed"

        queued = client.post(f"/api/v1/pipelines/{pipeline['id']}/runs", json={"trigger_kind": "manual", "input_payload": {"message": "cancel me"}})
        assert queued.status_code == 201
        cancelled = client.post(f"/api/v1/runs/{queued.json()['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        retried = client.post(f"/api/v1/runs/{queued.json()['id']}/retry")
        assert retried.status_code == 201
        assert retried.json()["status"] == "queued"
        assert client.post(f"/api/v1/runs/{retried.json()['id']}/cancel").status_code == 200

        assert client.delete(f"/api/v1/agents/{agent['id']}").status_code == 409
        assert client.delete(f"/api/v1/pipelines/{pipeline['id']}").status_code == 204
        assert all(item["id"] != pipeline["id"] for item in client.get("/api/v1/pipelines").json())
        history = client.get("/api/v1/runs").json()
        assert any(item["pipeline_name"] == "Worker test renamed (deleted)" for item in history)
        run_page = client.get("/api/v1/runs/page", params={"page": 1}).json()
        assert run_page["page_size"] == 20
        assert len(run_page["items"]) <= 20
        assert run_page["total"] >= len(run_page["items"])
        succeeded_page = client.get("/api/v1/runs/page", params={"status": "succeeded"}).json()
        assert all(item["status"] == "succeeded" for item in succeeded_page["items"])
        run_filters = client.get("/api/v1/runs/filter-options").json()
        assert "Worker test renamed (deleted)" in run_filters["pipelines"]
        assert agent["name"] in run_filters["agents"]

        legacy_pipeline = client.post("/api/v1/pipelines", json={
            "name": "Legacy fallback",
            "slug": f"legacy-{uuid.uuid4().hex[:8]}",
            "description": "rollback test",
            "visibility": "private",
            "graph": graph,
            "input_schema": {},
            "engine": "legacy",
        }).json()
        assert legacy_pipeline["engine"] == "legacy"
        legacy_run = client.post(f"/api/v1/pipelines/{legacy_pipeline['id']}/runs", json={"trigger_kind": "manual", "input_payload": {}}).json()
        assert legacy_run["engine"] == "legacy"
        legacy_claim = client.post("/api/v1/worker/jobs/claim", json={}, headers={"Authorization": f"Bearer {worker_token}"})
        assert legacy_claim.status_code == 200
        assert client.post(
            f"/api/v1/worker/jobs/{legacy_claim.json()['id']}/complete",
            json={"lease_token": legacy_claim.json()["lease_token"], "success": True, "output_payload": {}, "error": ""},
            headers={"Authorization": f"Bearer {worker_token}"},
        ).status_code == 204
        assert client.get(f"/api/v1/runs/{legacy_run['id']}").json()["status"] == "succeeded"
        assert client.delete(f"/api/v1/pipelines/{legacy_pipeline['id']}").status_code == 204
        assert client.delete(f"/api/v1/agents/{agent['id']}").status_code == 204

        assert client.delete(f"/api/v1/workers/{worker_id}").status_code == 204
        assert all(item["id"] != worker_id for item in client.get("/api/v1/workers").json())
