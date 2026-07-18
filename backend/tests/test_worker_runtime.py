import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routers.workers import _normalize_named_output


def load_worker():
    path = Path(__file__).parents[1] / "app" / "static" / "agent-forge-worker"
    loader = importlib.machinery.SourceFileLoader("agent_forge_worker_runtime", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_process_stdout_is_wrapped_for_single_output(monkeypatch) -> None:
    worker = load_worker()
    logs = []
    monkeypatch.setattr(
        worker, "emit", lambda _config, _job, message, level="info": logs.append((level, message))
    )
    job = {
        "id": "job-1",
        "input_payload": {},
        "config": {
            "draft_config": {
                "language": "bash",
                "code": "printf 'hello from bash\\n'",
                "timeout_seconds": 10,
            },
            "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
        },
    }
    assert worker.run_process({}, job) == {"result": "hello from bash"}
    assert any("stdout | hello from bash" in message for _, message in logs)
    assert any("automaticky mapujem" in message for _, message in logs)


def test_process_accepts_json_object_from_stdout(monkeypatch) -> None:
    worker = load_worker()
    monkeypatch.setattr(worker, "emit", lambda *_args, **_kwargs: None)
    job = {
        "id": "job-2",
        "input_payload": {},
        "config": {
            "draft_config": {
                "language": "bash",
                "code": 'printf \'{"date":"2026-07-16"}\\n\'',
                "timeout_seconds": 10,
            },
            "output_schema": {"type": "object", "properties": {"date": {"type": "string"}}},
        },
    }
    assert worker.run_process({}, job) == {"date": "2026-07-16"}


def test_process_replaces_invalid_utf8_without_failing(monkeypatch) -> None:
    worker = load_worker()
    monkeypatch.setattr(worker, "emit", lambda *_args, **_kwargs: None)
    job = {
        "id": "job-3",
        "input_payload": {},
        "config": {
            "draft_config": {"language": "bash", "code": "printf '\\341'", "timeout_seconds": 10},
            "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
        },
    }
    assert worker.run_process({}, job) == {"result": "�"}


def test_named_outputs_are_preserved_without_positional_fallback() -> None:
    run = SimpleNamespace(
        graph_snapshot={
            "nodes": [{"id": "writer", "data": {"outputs": [{"name": "result"}, {"name": "vtip"}]}}]
        }
    )
    step = SimpleNamespace(node_id="writer")
    output = _normalize_named_output(run, step, {"result": "default", "vtip": "správny vtip"})
    assert output == {"result": "default", "vtip": "správny vtip"}
    with pytest.raises(ValueError, match="vtip"):
        _normalize_named_output(run, step, {"result": "iba default"})


def test_builtin_transform_uses_declared_output_name() -> None:
    worker = load_worker()
    job = {
        "input_payload": {"vtip": "named value"},
        "config": {
            "node_kind": "transform",
            "node_config": {"expression": "$input.vtip"},
            "output_schema": {"type": "object", "properties": {"vtip": {"type": "string"}}},
        },
    }
    assert worker.builtin(job) == {"vtip": "named value"}


def test_empty_process_without_outputs_is_noop(monkeypatch) -> None:
    worker = load_worker()
    monkeypatch.setattr(worker, "emit", lambda *_args, **_kwargs: None)
    job = {
        "input_payload": {},
        "config": {
            "draft_config": {"language": "bash", "code": ""},
            "output_schema": {"type": "object", "properties": {}},
        },
    }
    assert worker.run_process({}, job) == {}


def test_multiline_stdout_is_structured_for_json_port(monkeypatch) -> None:
    worker = load_worker()
    monkeypatch.setattr(worker, "emit", lambda *_args, **_kwargs: None)
    job = {
        "id": "job-json-block",
        "input_payload": {},
        "config": {
            "draft_config": {
                "language": "bash",
                "code": "printf 'file-a\\nfile-b\\n'",
                "timeout_seconds": 10,
            },
            "output_schema": {"type": "object", "properties": {"result": {"type": "json"}}},
        },
    }
    assert worker.run_process({}, job) == {"result": {"object": "file-a\nfile-b"}}


def test_json_stdout_is_wrapped_under_single_named_json_port(monkeypatch) -> None:
    worker = load_worker()
    monkeypatch.setattr(worker, "emit", lambda *_args, **_kwargs: None)
    job = {
        "id": "job-json-object",
        "input_payload": {},
        "config": {
            "draft_config": {
                "language": "bash",
                "code": 'printf \'{"file":"a"}\'',
                "timeout_seconds": 10,
            },
            "output_schema": {"type": "object", "properties": {"result": {"type": "json"}}},
        },
    }
    assert worker.run_process({}, job) == {"result": {"file": "a"}}


def test_mcp_stdio_returns_named_structured_content(monkeypatch) -> None:
    worker = load_worker()
    monkeypatch.setattr(worker, "emit", lambda *_args, **_kwargs: None)
    server = Path(__file__).parent / "fixtures" / "fake_mcp_stdio.py"
    job = {
        "id": "mcp-stdio",
        "input_payload": {"value": "named pong"},
        "config": {
            "draft_config": {"timeout_seconds": 10},
            "output_schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
            "mcp": {
                "transport": "stdio",
                "command": [sys.executable, str(server)],
                "environment": {},
                "tool_name": "echo",
                "server_name": "fake",
            },
        },
    }
    assert worker.run_mcp({}, job) == {"answer": "named pong"}


def test_mcp_tool_error_is_distinct_from_transport_error(monkeypatch) -> None:
    worker = load_worker()
    monkeypatch.setattr(worker, "emit", lambda *_args, **_kwargs: None)
    server = Path(__file__).parent / "fixtures" / "fake_mcp_stdio.py"
    job = {
        "id": "mcp-error",
        "input_payload": {"fail": True},
        "config": {
            "draft_config": {"timeout_seconds": 10},
            "output_schema": {"type": "object", "properties": {"result": {"type": "json"}}},
            "mcp": {
                "transport": "stdio",
                "command": [sys.executable, str(server)],
                "environment": {},
                "tool_name": "fail",
                "server_name": "fake",
            },
        },
    }
    with pytest.raises(RuntimeError, match="MCP_TOOL_ERROR: requested failure"):
        worker.run_mcp({}, job)


def test_crewai_executor_keeps_named_output_and_emits_task_events(monkeypatch) -> None:
    worker = load_worker()
    logs = []
    monkeypatch.setattr(
        worker, "emit", lambda _config, _job, message, level="info": logs.append((level, message))
    )

    class FakeLLM:
        def __init__(self, **kwargs):
            self.options = kwargs

    class FakeAgent:
        def __init__(self, **kwargs):
            self.options = kwargs

    class FakeTask:
        def __init__(self, **kwargs):
            self.options = kwargs

    class FakeOutput:
        def model_dump(self):
            return {"vtip": "pomenovaný výsledok", "score": 0.9}

    class FakeCrewResult:
        pydantic = FakeOutput()

    class FakeCrew:
        def __init__(self, **kwargs):
            self.options = kwargs

        def kickoff(self, inputs):
            assert inputs == {"tema": "Linux"}
            for task in self.options["tasks"]:
                task.options["callback"](SimpleNamespace())
            return FakeCrewResult()

    fake_crewai = SimpleNamespace(
        Agent=FakeAgent,
        Crew=FakeCrew,
        LLM=FakeLLM,
        Process=SimpleNamespace(sequential="sequential", hierarchical="hierarchical"),
        Task=FakeTask,
    )
    monkeypatch.setitem(sys.modules, "crewai", fake_crewai)
    job = {
        "id": "crew-job",
        "input_payload": {"tema": "Linux"},
        "config": {
            "provider": {
                "kind": "ollama",
                "base_url": "http://127.0.0.1:11434",
                "model": "test",
                "api_key": None,
            },
            "draft_config": {
                "process": "sequential",
                "members": [{"role": "Autor", "goal": "Písať", "backstory": "Skúsený autor"}],
                "tasks": [
                    {
                        "name": "Vtip",
                        "description": "Napíš o {tema}",
                        "expected_output": "Vtip",
                        "agent_role": "Autor",
                    }
                ],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "vtip": {"x-agentforge-type": "string"},
                    "score": {"x-agentforge-type": "number"},
                },
                "required": ["vtip", "score"],
            },
        },
    }
    assert worker.run_crewai({"url": "http://127.0.0.1:8080"}, job) == {
        "vtip": "pomenovaný výsledok",
        "score": 0.9,
    }
    assert any("task dokončený: Vtip" in message for _, message in logs)
