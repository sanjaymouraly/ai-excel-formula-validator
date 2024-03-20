import httpx
import pytest

from app.core.models import ProviderProfile
from app.providers.client import ProviderClient, ProviderError


def profile(**kwargs):
    return ProviderProfile(
        name="test", kind="compatible", base_url="https://provider.example/v1", **kwargs
    )


def test_no_network_without_opt_in(store):
    client = ProviderClient(store)
    with pytest.raises(ProviderError, match="explicitly"):
        client.generate(profile(model="confirmed"), "sum")


def test_offline_fixture_is_explicit(store):
    result = ProviderClient(store).generate(
        ProviderProfile(name="offline", kind="offline"), "anything"
    )
    assert result["formula"] == "=SUM(B2:B100)"
    assert "not a generated AI prediction" in result["notice"]


def test_model_discovery_and_openai_adapter(store, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "secret-for-test")
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer secret-for-test"
        if request.url.path.endswith("models"):
            return httpx.Response(
                200, json={"data": [{"id": "confirmed-z"}, {"id": "confirmed-a"}]}
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "=SUM(B2:B100)"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 8},
            },
        )

    result = ProviderClient(store, httpx.MockTransport(handler)).generate(
        profile(input_per_million=1, output_per_million=2), "Sum B", True
    )
    assert result["model"] == "confirmed-a"
    assert result["estimated_cost_usd"] == 26 / 1e6
    assert len(seen) == 2


@pytest.mark.parametrize(
    "kind,path,response",
    [
        (
            "anthropic",
            "/v1/messages",
            {
                "content": [{"type": "text", "text": "=1+2"}],
                "usage": {"input_tokens": 5, "output_tokens": 4},
            },
        ),
        (
            "ollama",
            "/v1/api/chat",
            {"message": {"content": "=1+2"}, "prompt_eval_count": 5, "eval_count": 4},
        ),
        ("openrouter", "/v1/chat/completions", {"choices": [{"message": {"content": "=1+2"}}]}),
    ],
)
def test_other_protocols(store, monkeypatch, kind, path, response):
    monkeypatch.setenv("AI_API_KEY", "secret-for-test")

    def handler(request):
        assert request.url.path == path
        if kind == "anthropic":
            assert request.headers["x-api-key"] == "secret-for-test"
        return httpx.Response(200, json=response)

    p = ProviderProfile(
        name="test", kind=kind, base_url="https://provider.example/v1", model="confirmed-by-test"
    )
    assert (
        ProviderClient(store, httpx.MockTransport(handler)).generate(p, "Add", True)["formula"]
        == "=1+2"
    )


def test_retry_rate_limit_and_redacted_error(store, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "secret-for-test")
    monkeypatch.setattr("app.providers.client.time.sleep", lambda _: None)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(429, json={"secret": "do-not-log"})

    with pytest.raises(ProviderError) as exc:
        ProviderClient(store, httpx.MockTransport(handler)).generate(
            profile(model="confirmed"), "Sum", True
        )
    assert len(seen) == 3
    assert "do-not-log" not in str(exc.value)
    assert "secret-for-test" not in str(exc.value)


def test_budgets_and_limits(store, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "secret-for-test")
    client = ProviderClient(store)
    with pytest.raises(ProviderError, match="Budget"):
        client.generate(profile(model="confirmed", budget_usd=0.01), "Sum", True)
    store.record_usage("test", {"cost_reserved": 0})
    with pytest.raises(ProviderError, match="limit"):
        client.generate(profile(model="confirmed", request_limit=1), "Sum", True)


def test_discovery_failure_does_not_invent_model(store, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "secret-for-test")
    client = ProviderClient(store, httpx.MockTransport(lambda _: httpx.Response(404)))
    with pytest.raises(ProviderError, match="Supply a confirmed"):
        client.generate(profile(), "Sum", True)


def test_nested_usage_details_and_null_response_handling(store, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "secret-for-test")
    data = {
        "choices": [{"message": {"content": "=1+2"}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "completion_tokens_details": {"reasoning_tokens": 2},
        },
    }
    client = ProviderClient(store, httpx.MockTransport(lambda _: httpx.Response(200, json=data)))
    result = client.generate(profile(model="confirmed"), "sum", True)
    assert result["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}
    data["choices"][0]["message"]["content"] = None
    with pytest.raises(ProviderError, match="plain text"):
        client.generate(profile(model="confirmed"), "sum", True)


def test_base_url_must_not_contain_credentials():
    from app.providers.client import endpoint

    with pytest.raises(ProviderError):
        endpoint(
            ProviderProfile(
                name="unsafe", kind="compatible", base_url="https://key:secret@example.com/v1"
            )
        )
