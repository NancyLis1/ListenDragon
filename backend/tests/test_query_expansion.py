import json

import httpx
import pytest

from listen_dragon.services.query_expansion import OpenAIQueryExpander, normalize_query


def provider(handler):
    return OpenAIQueryExpander(
        base_url="https://example.test/v1", api_key="test-only-secret", model="qwen-test",
        transport=httpx.MockTransport(handler),
    )


def response(queries, **overrides):
    choice = {"finish_reason": "stop", "message": {"content": json.dumps({"queries": queries})}}
    choice.update(overrides)
    return httpx.Response(200, json={"choices": [choice]})


def test_original_retained_deduplicated_and_bounded():
    def handler(request):
        assert request.url == "https://example.test/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["enable_thinking"] is False
        assert payload["messages"][1]["content"] == "What is RRF?"
        return response(["what is rrf?", "", 123, "x" * 1001, "解释 RRF", "RRF 原理", "extra"])

    result = provider(handler).expand("  What is RRF? \n")
    assert result.queries == ("What is RRF?", "解释 RRF", "RRF 原理")
    assert result.fallback_reason is None


@pytest.mark.parametrize("query", ["", " \n ", "x" * 1001, None, 42])
def test_invalid_user_query_rejected(query):
    with pytest.raises((TypeError, ValueError)):
        normalize_query(query)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
def test_http_failure_does_not_leak_provider_body(status):
    result = provider(lambda _: httpx.Response(status, text="private provider diagnostic")).expand("Q")
    assert result.queries == ("Q",)
    assert result.fallback_reason == "http_error"
    assert "private" not in repr(result)


@pytest.mark.parametrize("error,code", [
    (httpx.ReadTimeout("secret"), "timeout"),
    (httpx.ConnectError("secret"), "connection_error"),
])
def test_network_failure_falls_back(error, code):
    def handler(_):
        raise error

    assert provider(handler).expand("Q").fallback_reason == code


@pytest.mark.parametrize("value", [None, [], {}, {"choices": []}, {"choices": [None]}])
def test_malformed_envelope_falls_back(value):
    assert provider(lambda _: httpx.Response(200, json=value)).expand("Q").fallback_reason == (
        "invalid_response"
    )


@pytest.mark.parametrize("queries,reason", [
    ({"bad": "shape"}, "invalid_response"), ([], "no_rewrites"),
    ([None, "", "Q"], "no_rewrites"),
])
def test_invalid_or_empty_rewrites(queries, reason):
    assert provider(lambda _: response(queries)).expand("Q").fallback_reason == reason


def test_incomplete_and_oversized_response():
    assert provider(lambda _: response(["rewrite"], finish_reason="length")).expand(
        "Q"
    ).fallback_reason == "incomplete_response"
    assert provider(lambda _: httpx.Response(200, content=b"x" * 65537)).expand(
        "Q"
    ).fallback_reason == "response_too_large"
    assert provider(lambda _: httpx.Response(200, content=b"[" * 2000 + b"]" * 2000)).expand(
        "Q"
    ).fallback_reason == "invalid_response"


def test_disabled_and_unconfigured_do_not_call_network():
    assert OpenAIQueryExpander(enabled=False).expand("Q").fallback_reason == "disabled"
    assert OpenAIQueryExpander().expand("Q").fallback_reason == "not_configured"


def test_generic_provider_does_not_receive_qwen_option():
    def handler(request):
        assert "enable_thinking" not in json.loads(request.content)
        return response(["rewrite"])

    expander = provider(handler)
    expander.model = "local-model"
    assert expander.expand("Q").queries == ("Q", "rewrite")
