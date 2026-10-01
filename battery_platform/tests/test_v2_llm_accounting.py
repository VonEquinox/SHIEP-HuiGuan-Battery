"""Provider failures retain known cost and explicitly expose unknown usage."""
from __future__ import annotations

import json

import httpx
import pytest

from app.agent import LLMError, OpenAICompatibleClient, run_agent

USAGE = {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
MESSAGES = [{"role": "user", "content": "Return JSON"}]


@pytest.mark.parametrize("body", [
    {"usage": USAGE},
    {"usage": USAGE, "choices": [{"message": {"content": "{broken"}}]},
    {"usage": USAGE, "choices": [{"message": {"content": "[]"}}]},
    {"usage": USAGE, "choices": [{"message": None}]},
])
def test_invalid_completion_counts_failure_once_and_retains_known_usage(body):
    client = OpenAICompatibleClient(api_key="test-only", retries=0,
                                   transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))
    with pytest.raises(LLMError):
        client.generate_json(MESSAGES)
    client.mark_response_failed()  # A caller validating the same response must not double count.
    assert client.request_count == client.failed_request_count == 1
    assert client.last_usage == client.total_usage == USAGE
    assert client.unknown_usage_request_count == 0


def test_malformed_http_json_has_unknown_usage_and_resets_previous_last_usage():
    responses = iter([httpx.Response(200, json={"usage": USAGE, "choices": [{"message": {"content": "{}"}}]}),
                      httpx.Response(200, text="not JSON")])
    client = OpenAICompatibleClient(api_key="test-only", retries=0,
                                   transport=httpx.MockTransport(lambda _: next(responses)))
    assert client.generate_json(MESSAGES) == {}
    with pytest.raises(LLMError):
        client.generate_json(MESSAGES)
    assert client.request_count == 2 and client.failed_request_count == 1
    assert client.last_usage == {} and client.total_usage == USAGE
    assert client.unknown_usage_request_count == 1 and not client.last_response_metadata["usage_known"]


def test_retried_http_failure_cost_is_separate_from_success():
    responses = iter([httpx.Response(503, json={"usage": USAGE}),
                      httpx.Response(200, json={"usage": USAGE, "choices": [{"message": {"content": "{}"}}]})])
    client = OpenAICompatibleClient(api_key="test-only", retries=1,
                                   transport=httpx.MockTransport(lambda _: next(responses)))
    assert client.generate_json(MESSAGES) == {}
    assert client.request_count == 2 and client.failed_request_count == 1
    assert client.total_usage == {key: value * 2 for key, value in USAGE.items()}
    assert client.unknown_usage_request_count == 0


def test_thinking_setting_is_opt_in_and_uses_documented_provider_field(monkeypatch):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"usage": USAGE, "choices": [{"message": {"content": "{}"}}]})
    monkeypatch.setenv("BATTERY_LLM_API_KEY", "test-only")
    monkeypatch.delenv("BATTERY_LLM_THINKING", raising=False)
    client = OpenAICompatibleClient.from_env()
    client.transport = httpx.MockTransport(handler)
    client.generate_json(MESSAGES)
    assert "thinking" not in requests[-1]
    monkeypatch.setenv("BATTERY_LLM_THINKING", "disabled")
    client = OpenAICompatibleClient.from_env()
    client.transport = httpx.MockTransport(handler)
    client.generate_json(MESSAGES)
    assert requests[-1]["thinking"] == {"type": "disabled"} and requests[-1]["max_tokens"] == 4096
    monkeypatch.setenv("BATTERY_LLM_THINKING", "arbitrary")
    with pytest.raises(ValueError, match="thinking"):
        OpenAICompatibleClient.from_env()


def test_executor_complete_path_retains_invalid_json_failure_and_unknown_usage():
    client = OpenAICompatibleClient(api_key="test-only", retries=0,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "{broken"}}]})))
    result = run_agent({"asset_id": "a", "installation_id": "i", "visible_cutoff": "2026-09-01T00:00:00Z"}, llm=client)
    assert not result["run"]["cloud_report_valid"]
    assert result["run"]["llm_request_count"] == result["run"]["llm_failed_request_count"] == 1
    assert result["run"]["llm_unknown_usage_request_count"] == 1
