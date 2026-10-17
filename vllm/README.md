# vllm

Same SuperGrid pattern as [`../ollama`](../ollama), but each SuperNode calls a
local [vLLM](https://docs.vllm.ai) OpenAI-compatible server instead of Ollama.

## Setup (on every SuperNode machine)

```bash
pip install vllm            # needs a supported GPU/CPU build, see vLLM docs
vllm serve Qwen/Qwen2.5-0.5B-Instruct --port 8000
pip install -e .            # from this directory
```

## Run

Start the SuperLink and SuperNodes exactly as in
[`../ollama/TESTING.md`](../ollama/TESTING.md), then from this directory:

```bash
flwr run . supergrid --stream
```

Override config at runtime, e.g.:

```bash
flwr run . supergrid --stream --run-config 'prompt="Hello" max-tokens=64'
```

The `model` config must match the model passed to `vllm serve`.
