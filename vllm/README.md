# vllm

SuperGrid LLM inference where each SuperNode calls a
local [vLLM](https://docs.vllm.ai) OpenAI-compatible server. See the
[top-level README](../README.md) for the architecture and message flow.

## Setup (on every SuperNode machine)

```bash
pip install vllm            # needs a supported GPU/CPU build, see vLLM docs
vllm serve Qwen/Qwen2.5-0.5B-Instruct --port 8000
pip install -e .            # from this directory
```

## Run

Start the SuperLink and SuperNodes as described in the
[top-level README](../README.md#running-the-grid), then from this directory:

```bash
flwr run . supergrid --stream
```

Override config at runtime, e.g.:

```bash
flwr run . supergrid --stream --run-config 'prompt="Hello" max-tokens=64'
```

## Config

Set in `[tool.flwr.app.config]` in [pyproject.toml](pyproject.toml):

| Key | Default | Meaning |
|---|---|---|
| `model` | `Qwen/Qwen2.5-0.5B-Instruct` | Model name; must match what `vllm serve` loaded |
| `vllm-url` | `http://127.0.0.1:8000/v1` | Base URL of the node-local vLLM server |
| `max-tokens` | `128` | Max tokens generated per reply |
| `prompt` | `In one sentence, what is federated learning?` | Prompt sent to all nodes |
