# vllm

SuperGrid LLM inference where each SuperNode calls a
local [vLLM](https://docs.vllm.ai) OpenAI-compatible server. See the
[top-level README](../README.md) for the architecture and message flow.

## Setup

Complete the [install and grid quick test](../README.md#install) first. Then, on
every SuperNode machine:

```bash
uv pip install -e .         # install this app into the Flower venv
```

The vLLM server is a separate program, so install it **outside** the Flower
venv (it pins its own torch/CUDA versions). On Linux, in its own venv:

```bash
uv venv --python 3.12 ~/.venvs/vllm
uv pip install --python ~/.venvs/vllm/bin/python vllm
```

Then keep a vLLM server running on each SuperNode machine (separate terminal):

```bash
~/.venvs/vllm/bin/vllm serve Qwen/Qwen2.5-0.5B-Instruct --port 8000
```

> **macOS (Apple Silicon):** upstream vLLM has no macOS wheels, so don't build it
> from source. Use [vLLM-Metal](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/),
> the Apple Silicon (MLX/Metal) backend, following its install steps. It serves
> MLX models, e.g. `mlx-community/Qwen2.5-0.5B-Instruct-4bit`; set `model` in
> [pyproject.toml](pyproject.toml) to match what you serve.

## Run

With the SuperLink and SuperNodes running (see the
[quick test](../README.md#quick-test-join-nodes-to-the-grid)) and `vllm serve`
up on each SuperNode, from this directory:

```bash
flwr run . selfhosted --stream
```

Override config at runtime, e.g.:

```bash
flwr run . selfhosted --stream --run-config 'prompt="{YOUR PROMPT}" max-tokens=64'
```

## Config

Set in `[tool.flwr.app.config]` in [pyproject.toml](pyproject.toml):

| Key | Default | Meaning |
|---|---|---|
| `model` | `Qwen/Qwen2.5-0.5B-Instruct` | Model name; must match what `vllm serve` loaded |
| `vllm-url` | `http://127.0.0.1:8000/v1` | Base URL of the node-local vLLM server |
| `max-tokens` | `128` | Max tokens generated per reply |
| `prompt` | `In one sentence, what is federated learning?` | Prompt sent to all nodes |
