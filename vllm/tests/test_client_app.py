import json
from types import SimpleNamespace

import pytest

from supergrid_vllm import client_app
from supergrid_vllm.client_app import complete, resolve_model, run_batch


class FakeClient:
    def __init__(self, usage=SimpleNamespace(prompt_tokens=7, completion_tokens=20), models=("served-model",)):
        self.calls = []
        self.models = SimpleNamespace(
            list=lambda: SimpleNamespace(data=[SimpleNamespace(id=m) for m in models])
        )
        message = SimpleNamespace(content="the answer")
        result = SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

        def create(**kwargs):
            self.calls.append(kwargs)
            return result

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def test_model_resolution_order():
    client = FakeClient()
    assert resolve_model(client, {"model": "node"}, {"model": "run"}) == "node"
    assert resolve_model(client, {}, {"model": "run"}) == "run"
    assert resolve_model(client, {}, {"model": ""}) == "served-model"
    assert resolve_model(client, {}, {}) == "served-model"


def test_complete_returns_metrics_and_uses_temperature_zero():
    client = FakeClient()
    out = complete(client, "m", "hi", max_tokens=64)
    assert set(out) == {
        "response", "model", "latency_s", "prompt_tokens", "completion_tokens", "tokens_per_s",
    }
    assert out["response"] == "the answer" and out["model"] == "m"
    assert (out["prompt_tokens"], out["completion_tokens"]) == (7, 20)
    assert out["tokens_per_s"] == pytest.approx(20 / out["latency_s"])
    assert client.calls[0]["temperature"] == 0 and client.calls[0]["max_tokens"] == 64


def test_missing_usage_gives_zero_tokens_without_error():
    out = complete(FakeClient(usage=None), "m", "hi", max_tokens=8)
    assert out["completion_tokens"] == 0 and out["tokens_per_s"] == 0


def test_zero_latency_does_not_divide_by_zero(monkeypatch):
    monkeypatch.setattr(client_app.time, "perf_counter", lambda: 1.0)
    assert complete(FakeClient(), "m", "hi", max_tokens=8)["tokens_per_s"] == 0.0


def test_batch_runs_prompts_in_order_and_isolates_failures():
    client = FakeClient()
    original = client.chat.completions.create

    def flaky(**kwargs):
        if kwargs["messages"][0]["content"] == "bad":
            raise ValueError("context too long")
        return original(**kwargs)

    client.chat.completions.create = flaky
    results = run_batch(client, "m", ["first", "bad", "last"], max_tokens=8)
    assert [("error" in r) for r in results] == [False, True, False]
    assert results[1]["error"] == "ValueError: context too long"
    assert results[2]["response"] == "the answer"


def test_query_returns_one_json_result_per_prompt(monkeypatch):
    monkeypatch.setattr(client_app, "OpenAI", lambda **kw: FakeClient())
    ctx = SimpleNamespace(
        node_config={"model": "node-model"},
        run_config={"vllm-url": "http://x/v1", "max-tokens": 8, "model": "run-model"},
    )
    # A real reply needs a Flower run identity, so stand in for Message here.
    monkeypatch.setattr(
        client_app, "Message", lambda content, reply_to: SimpleNamespace(content=content)
    )
    msg = SimpleNamespace(content={"config": {"prompts": json.dumps(["a", "b"])}})
    reply = client_app.query(msg, ctx)
    config = reply.content["config"]
    results = json.loads(config["results"])
    assert [r["model"] for r in results] == ["node-model", "node-model"]
    assert config["compute_s"] >= 0


def test_backend_error_becomes_readable_runtime_error(monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(client_app, "OpenAI", lambda **kw: SimpleNamespace(models=SimpleNamespace(list=boom)))
    ctx = SimpleNamespace(
        node_config={},
        run_config={"vllm-url": "http://x/v1", "max-tokens": 8, "model": ""},
    )
    msg = SimpleNamespace(content={"config": {"prompts": json.dumps(["hi"])}})
    with pytest.raises(RuntimeError, match=r"http://x/v1 failed \(ConnectionError\): connection refused"):
        client_app.query(msg, ctx)
