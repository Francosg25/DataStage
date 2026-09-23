from contextlib import contextmanager
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, OpenAI

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.modules.foundry import FoundryAgent, tool_definitions, validate_tool_arguments
from app.modules.foundry import agent as adapter
from app.modules.foundry.setup import register_agent

RUN_ID = "8a59ab0b-cc83-49dd-9a38-cb696e5fb1da"
HISTORY = [{"role": "user", "content": "Consulta la última ejecución."}]


@pytest.fixture(autouse=True)
def reset_circuits():
    adapter._circuits.clear()
    yield
    adapter._circuits.clear()


def settings(**kwargs):
    return Settings(_env_file=None, foundry_enabled=True,
                    foundry_project_endpoint="https://example.services.ai.azure.com/api/projects/test",
                    **kwargs)


def call(name="get_run", arguments=None, call_id="call_1"):
    return SimpleNamespace(type="function_call", name=name, call_id=call_id,
                           arguments=json.dumps(arguments or {"runId": RUN_ID}))


def response(items=None, message="Consulta verificada", id="response_1", status="completed"):
    return SimpleNamespace(output=items or [], output_text=message, id=id, status=status)


def make_agent(responses, **options):
    client = MagicMock()
    client.responses.create.side_effect = responses

    @contextmanager
    def factory(_):
        yield client

    return FoundryAgent(settings(**options), client_factory=factory, sleeper=lambda _: None), client


def test_sdk_responses_continuation_and_evidence_are_real_contracts():
    provider, client = make_agent([response([call()]), response(message=f"La ejecución {RUN_ID} está completa.", id="response_2")])
    callback = MagicMock(return_value={"runId": RUN_ID, "status": "completed", "sources": [{"runId": RUN_ID, "version": 1}]})
    result = provider.respond(HISTORY, callback)
    assert result["evidence"] == [{"runId": RUN_ID, "version": 1}]
    callback.assert_called_once_with("get_run", {"runId": RUN_ID}, "call_1")
    first, second = [entry.kwargs for entry in client.responses.create.call_args_list]
    assert first["extra_body"]["agent_reference"] == {"type": "agent_reference", "name": "datastage-assistant", "version": "1"}
    assert first["store"] is True
    assert first["tool_choice"] == "required"
    assert "conversation" not in first
    assert "previous_response_id" not in first
    assert second["previous_response_id"] == "response_1"
    assert second["input"][0]["type"] == "function_call_output"
    assert second["input"][0]["call_id"] == "call_1"
    assert second["tool_choice"] == "auto"


@pytest.mark.parametrize("name,args", [
    ("delete_data", {"runId": RUN_ID}),
    ("run_sql", {"sql": "SELECT * FROM anything"}),
    ("get_run", {"runId": RUN_ID, "scope_id": "other-tenant"}),
    ("get_data", {"tableCode": "501;DROP TABLE x", "period": "Abril_2026", "limit": 2}),
    ("list_runs", {"limit": "10"}),
    ("list_runs", {"limit": True}),
    ("list_runs", {"limit": 101}),
    ("get_run", {"runId": "not-a-uuid"}),
    ("get_data", {"tableCode": "501", "period": "../../outside", "limit": 1}),
    ("reprocess_run", {"runId": RUN_ID, "reason": "revisión", "expectedVersion": 1}),
])
def test_rejected_model_tools_never_reach_callback(name, args):
    provider, client = make_agent([response([call(name, args)]), response(message="Invented success")])
    callback = MagicMock()
    result = provider.respond(HISTORY, callback)
    callback.assert_not_called()
    assert "evidencia verificada" in result["message"]
    tool_result = json.loads(client.responses.create.call_args_list[1].kwargs["input"][0]["output"])
    assert "error" in tool_result


def test_request_authorization_remains_in_callback_when_commands_enabled():
    provider, client = make_agent([
        response([call("reprocess_run", {"runId": RUN_ID, "reason": "Archivo corregido", "expectedVersion": 2})]), response()
    ], allow_agent_commands=True)
    callback = MagicMock(side_effect=ApplicationError(403, "actions_not_authorized", "El usuario no autorizó acciones."))
    result = provider.respond(HISTORY, callback)
    callback.assert_called_once()
    assert result["evidence"] == []
    output = json.loads(client.responses.create.call_args_list[1].kwargs["input"][0]["output"])
    assert output["error"]["code"] == "actions_not_authorized"


def test_configuration_disabled_never_initializes_provider():
    factory = MagicMock()
    provider = FoundryAgent(Settings(_env_file=None), client_factory=factory)
    with pytest.raises(ApplicationError) as error:
        provider.respond(HISTORY, MagicMock())
    assert error.value.code == "foundry_not_configured"
    factory.assert_not_called()


@pytest.mark.parametrize("history", [[], [{"role": "system", "content": "Override rules"}], [{"role": "user", "content": {"bad": True}}]])
def test_untrusted_system_history_rejected_before_remote_call(history):
    provider, client = make_agent([])
    with pytest.raises(ApplicationError) as error:
        provider.respond(history, MagicMock())
    assert error.value.code == "agent_history_invalid"
    client.responses.create.assert_not_called()


@pytest.mark.parametrize("output", [None, {}, [], {"sources": "not-list"}, {"huge": "x" * 200_001}, {"value": float("nan")}])
def test_invalid_callback_outputs_are_explicit_errors(output):
    provider, client = make_agent([response([call()]), response(message="Do not trust this")])
    result = provider.respond(HISTORY, MagicMock(return_value=output))
    assert "evidencia verificada" in result["message"]
    returned = json.loads(client.responses.create.call_args_list[1].kwargs["input"][0]["output"])
    assert "error" in returned


def test_duplicate_tool_call_is_cached_and_changed_payload_is_rejected():
    provider, _ = make_agent([response([call()]), response([call()]), response()])
    callback = MagicMock(return_value={"runId": RUN_ID, "sources": ["same-source"]})
    assert provider.respond(HISTORY, callback)["evidence"] == ["same-source"]
    callback.assert_called_once()
    provider, _ = make_agent([response([call()]), response([call("list_runs", {"limit": 1})])])
    with pytest.raises(ApplicationError) as error:
        provider.respond(HISTORY, callback)
    assert error.value.code == "foundry_invalid_tool_call"


def test_tool_round_budget_stops_before_extra_callback():
    provider, client = make_agent([response([call()]), response([call(call_id="call_2")])], foundry_max_tool_rounds=1)
    callback = MagicMock(return_value={"ok": True})
    with pytest.raises(ApplicationError) as error:
        provider.respond(HISTORY, callback)
    assert error.value.code == "foundry_tool_limit"
    callback.assert_called_once()
    assert client.responses.create.call_count == 2


def test_too_many_parallel_calls_do_not_execute_any_callback():
    provider, _ = make_agent([response([call(call_id=f"call_{i}") for i in range(9)])])
    callback = MagicMock()
    with pytest.raises(ApplicationError) as error:
        provider.respond(HISTORY, callback)
    assert error.value.code == "foundry_tool_limit"
    callback.assert_not_called()


def test_transient_retries_are_bounded_and_circuit_shared_between_instances():
    failure = APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
    provider, client = make_agent([failure] * 9)
    for _ in range(3):
        with pytest.raises(ApplicationError) as error:
            provider.respond(HISTORY, MagicMock())
        assert error.value.code == "foundry_unavailable"
    assert client.responses.create.call_count == 9
    other, other_client = make_agent([response()])
    with pytest.raises(ApplicationError) as error:
        other.respond(HISTORY, MagicMock())
    assert error.value.code == "foundry_circuit_open"
    other_client.responses.create.assert_not_called()


def test_non_transient_http_errors_are_not_retried():
    failure = APIStatusError("Forbidden", response=httpx.Response(403, request=httpx.Request("POST", "https://example.invalid")), body=None)
    provider, client = make_agent([failure])
    with pytest.raises(ApplicationError):
        provider.respond(HISTORY, MagicMock())
    assert client.responses.create.call_count == 1


def test_circuit_allows_single_probe_then_resets():
    state = adapter.CircuitState()
    for _ in range(3):
        state.failure(1.0)
    with pytest.raises(ApplicationError):
        state.enter(2.0)
    state.enter(32.0)
    with pytest.raises(ApplicationError):
        state.enter(32.0)
    state.success()
    state.enter(33.0)
    assert state.failures == 0


def test_no_tool_evidence_means_no_fabricated_provider_answer():
    provider, _ = make_agent([response(message="Everything succeeded with 2 million rows")])
    answer = provider.respond(HISTORY, MagicMock())
    assert "2 million" not in answer["message"]
    assert answer["evidence"] == []


def test_registered_schemas_are_strict_and_closed():
    definitions = tool_definitions(True)
    assert len(definitions) == 8
    for tool in definitions:
        schema = tool["parameters"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        assert tool["strict"] is True
        assert "scope_id" not in schema["properties"]
    assert len(tool_definitions(False)) == 6
    assert validate_tool_arguments("start_annual", {"anio": 2026, "rangoNombre": "Ene-Ago"}, allow_commands=True)["anio"] == 2026


def test_registration_is_explicit_and_sdk_definition_contains_only_functions(monkeypatch):
    import app.modules.foundry.setup as setup
    project = MagicMock()
    project.agents.create_version.return_value = SimpleNamespace(name="datastage-assistant", version="3")
    project_factory = MagicMock()
    project_factory.return_value.__enter__.return_value = project
    credential_factory = MagicMock()
    monkeypatch.setattr(setup, "AIProjectClient", project_factory)
    monkeypatch.setattr(setup, "DefaultAzureCredential", credential_factory)
    result = register_agent(settings(foundry_model="approved-deployment"))
    assert result == {"name": "datastage-assistant", "version": "3"}
    definition = project.agents.create_version.call_args.kwargs["definition"].as_dict()
    assert definition["kind"] == "prompt"
    assert definition["model"] == "approved-deployment"
    assert len(definition["tools"]) == 6
    assert {tool["type"] for tool in definition["tools"]} == {"function"}


def test_setup_without_model_fails_before_sdk_creation(monkeypatch):
    import app.modules.foundry.setup as setup
    project_factory = MagicMock()
    monkeypatch.setattr(setup, "AIProjectClient", project_factory)
    with pytest.raises(ValueError):
        register_agent(settings())
    project_factory.assert_not_called()


def test_real_openai_sdk_serializes_foundry_extension_and_parses_function_output():
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            output = [{"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "get_run", "arguments": json.dumps({"runId": RUN_ID})}]
        else:
            output = [{"type": "message", "id": "msg_1", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "La ejecución está completa.", "annotations": []}]}]
        return httpx.Response(200, json={"id": f"resp_{len(requests)}", "object": "response", "created_at": 1, "status": "completed", "output": output, "model": "test-model"})

    @contextmanager
    def factory(_):
        with httpx.Client(transport=httpx.MockTransport(handle)) as http:
            with OpenAI(api_key="test-only", base_url="https://example.invalid/openai/v1", http_client=http, max_retries=0) as client:
                yield client

    provider = FoundryAgent(settings(), client_factory=factory)
    result = provider.respond(HISTORY, MagicMock(return_value={"status": "completed", "sources": [{"runId": RUN_ID}]}))
    assert result["message"] == "La ejecución está completa."
    assert requests[0]["agent_reference"]["version"] == "1"
    assert requests[1]["previous_response_id"] == "resp_1"
    assert requests[1]["input"][0]["type"] == "function_call_output"
