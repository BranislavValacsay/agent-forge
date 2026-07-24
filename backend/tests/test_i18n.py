from app.i18n import localize_detail
from app.schemas import RegisterRequest, WorkerJobEvent


def test_localizes_static_and_parameterized_api_errors() -> None:
    assert localize_detail("Agent not found", "sk-SK") == "Agent sa nenašiel"
    assert (
        localize_detail("MCP server files is disabled", "sk")
        == "MCP server files je zakázaný"
    )
    assert localize_detail("Agent not found", "en-US") == "Agent not found"


def test_locale_and_runtime_event_contracts_are_validated() -> None:
    registration = RegisterRequest(
        email="root@example.com",
        display_name="Root",
        password="long-enough-password",
        locale="en",
    )
    event = WorkerJobEvent(
        message="Starting process: bash agent.sh",
        message_key="runtime.processStart",
        message_params={"command": "bash agent.sh"},
    )
    assert registration.locale == "en"
    assert event.message_key == "runtime.processStart"
