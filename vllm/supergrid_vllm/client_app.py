"""ClientApp: answer a query using a locally-served vLLM model.

Each SuperNode runs its own vLLM OpenAI-compatible server (`vllm serve <model>`)
and this app calls it on localhost; no model weights or data leave the node.
It receives the whole prompt list in one message, runs the prompts one after
another and returns the response and timing metrics of each, so the grid is
crossed once per node however many prompts there are.
"""

import json
import time

from flwr.app import ConfigRecord, Context, Message, RecordDict
from flwr.clientapp import ClientApp
from openai import OpenAI

app = ClientApp()


def resolve_model(client, node_config, run_config) -> str:
    """Pick the model: node config, then run config, then the server's first model."""
    for config in (node_config, run_config):
        model = config.get("model")
        if model:
            return str(model)
    return client.models.list().data[0].id


def complete(client, model: str, prompt: str, max_tokens: int) -> dict:
    """Run one chat completion and return the response with its metrics."""
    start = time.perf_counter()
    result = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0,  # deterministic output keeps nodes comparable
    )
    latency_s = time.perf_counter() - start

    usage = result.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    return {
        "response": result.choices[0].message.content or "",
        "model": model,
        "latency_s": latency_s,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        # End-to-end: latency includes prompt processing, not only decoding.
        "tokens_per_s": completion_tokens / latency_s if latency_s > 0 else 0.0,
    }


def run_batch(client, model: str, prompts: list[str], max_tokens: int) -> list[dict]:
    """Run the prompts in order. A failed prompt is reported, not raised, so one
    bad prompt does not lose the results of the others."""
    results = []
    for prompt in prompts:
        try:
            results.append(complete(client, model, prompt, max_tokens))
        except Exception as err:
            results.append({"error": f"{type(err).__name__}: {err}"})
    return results


@app.query()
def query(msg: Message, context: Context) -> Message:
    base_url = context.run_config["vllm-url"]
    prompts = json.loads(msg.content["config"]["prompts"])

    client = OpenAI(base_url=base_url, api_key="EMPTY")
    try:
        model = resolve_model(client, context.node_config, context.run_config)
    except Exception as err:
        # Flower sends the exception text back as the error reply, so keep it readable.
        raise RuntimeError(
            f"vLLM request to {base_url} failed ({type(err).__name__}): {err}"
        ) from err

    start = time.perf_counter()
    results = run_batch(client, model, prompts, int(context.run_config["max-tokens"]))
    reply = {"results": json.dumps(results), "compute_s": time.perf_counter() - start}

    return Message(content=RecordDict({"config": ConfigRecord(reply)}), reply_to=msg)
