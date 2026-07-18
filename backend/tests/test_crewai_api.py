import asyncio
import os
import uuid

os.environ["AF_DATABASE_URL"] = "sqlite:///./test_agent_forge.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ModelCatalog, Provider, User  # noqa: E402
from app.routers.runs import stream_events  # noqa: E402
from app.security import hash_password  # noqa: E402


def test_crewai_agent_contract_and_worker_job() -> None:
    password = "a-long-crewai-test-password"
    email = f"crew-{uuid.uuid4()}@example.com"
    with TestClient(app) as client:
        with SessionLocal() as db:
            user = User(
                email=email,
                display_name="Crew Test",
                password_hash=hash_password(password),
                is_root=True,
            )
            db.add(user)
            db.flush()
            provider = Provider(
                name="Crew Ollama",
                kind="ollama",
                base_url="http://127.0.0.1:11434",
                enabled=True,
                created_by=user.id,
            )
            db.add(provider)
            db.flush()
            model = ModelCatalog(
                provider_id=provider.id,
                model_id="crew-test",
                display_name="Crew Test",
                capabilities={},
                enabled=True,
            )
            db.add(model)
            db.commit()
            provider_id, model_id = provider.id, model.id

        assert (
            client.post(
                "/api/v1/auth/login", json={"email": email, "password": password}
            ).status_code
            == 200
        )
        base_agent = {
            "name": "Editorial crew",
            "slug": f"crew-{uuid.uuid4().hex[:8]}",
            "description": "Crew contract test",
            "purpose": "Produce a named result",
            "kind": "crewai",
            "visibility": "private",
            "provider_id": provider_id,
            "model_catalog_id": model_id,
            "input_schema": {
                "type": "object",
                "properties": {"topic": {"x-agentforge-type": "string"}},
                "required": ["topic"],
            },
            "output_schema": {
                "type": "object",
                "properties": {"answer": {"x-agentforge-type": "string"}},
                "required": ["answer"],
            },
        }
        invalid = client.post(
            "/api/v1/agents",
            json={
                **base_agent,
                "draft_config": {"process": "sequential", "members": [], "tasks": []},
            },
        )
        assert invalid.status_code == 422

        created = client.post(
            "/api/v1/agents",
            json={
                **base_agent,
                "draft_config": {
                    "deployment_mode": "crewai",
                    "process": "sequential",
                    "members": [
                        {
                            "role": "Writer",
                            "goal": "Answer",
                            "backstory": "Experienced writer",
                            "allow_delegation": False,
                        }
                    ],
                    "tasks": [
                        {
                            "name": "Write",
                            "description": "Answer {topic}",
                            "expected_output": "Named answer",
                            "agent_role": "Writer",
                        }
                    ],
                },
            },
        )
        assert created.status_code == 201
        agent = created.json()

        token = client.post(
            "/api/v1/workers/registration-tokens",
            json={"name_hint": "crew-worker", "expires_in_minutes": 30},
        ).json()["token"]
        registration = client.post(
            "/api/v1/worker/register",
            json={
                "registration_token": token,
                "name": "crew-worker",
                "worker_class": "cpu",
                "executors": ["crewai"],
                "version": "0.6.0",
                "platform": "linux",
                "architecture": "x86_64",
            },
        ).json()
        headers = {"Authorization": f"Bearer {registration['worker_token']}"}
        graph = {
            "nodes": [
                {
                    "id": "crew",
                    "position": {"x": 0, "y": 0},
                    "data": {
                        "label": "Crew",
                        "nodeKind": "agent",
                        "agentId": agent["id"],
                        "agentName": agent["name"],
                        "inputs": [],
                        "outputs": [],
                    },
                }
            ],
            "edges": [],
        }
        pipeline = client.post(
            "/api/v1/pipelines",
            json={
                "name": "Crew pipeline",
                "slug": f"crew-pipeline-{uuid.uuid4().hex[:8]}",
                "visibility": "private",
                "graph": graph,
            },
        ).json()
        run = client.post(
            f"/api/v1/pipelines/{pipeline['id']}/runs",
            json={"trigger_kind": "manual", "input_payload": {"topic": "Linux"}},
        ).json()
        claim = client.post("/api/v1/worker/jobs/claim", json={}, headers=headers)
        assert claim.status_code == 200
        job = claim.json()
        assert job["executor"] == "crewai"
        assert job["input_payload"] == {"topic": "Linux"}
        assert job["config"]["provider"]["model"] == "crew-test"
        assert job["config"]["output_schema"]["required"] == ["answer"]
        assert (
            client.post(
                f"/api/v1/worker/jobs/{job['id']}/complete",
                json={
                    "lease_token": job["lease_token"],
                    "success": True,
                    "output_payload": {"answer": "OK"},
                    "error": "",
                },
                headers=headers,
            ).status_code
            == 204
        )
        assert client.get(f"/api/v1/runs/{run['id']}").json()["status"] == "succeeded"
        checked_out = engine.pool.checkedout()
        stream = asyncio.run(stream_events(run["id"], af_session=client.cookies.get("af_session")))
        assert engine.pool.checkedout() == checked_out
        asyncio.run(stream.body_iterator.aclose())
