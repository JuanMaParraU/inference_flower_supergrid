# ollama

SuperGrid LLM inference where each SuperNode calls a locally-served
[Ollama](https://ollama.com) model. See the [top-level README](../README.md)
for the architecture, message flow and how to start the grid, and
[TESTING.md](TESTING.md) for a single-machine walkthrough with experiments and
troubleshooting.

| File | Purpose |
|---|---|
| [supergrid_llm/server_app.py](supergrid_llm/server_app.py) | `ServerApp`: fans the prompt out to every SuperNode and prints replies |
| [supergrid_llm/client_app.py](supergrid_llm/client_app.py) | `ClientApp`: `@app.query()` handler that calls `ollama.generate` |
| [pyproject.toml](pyproject.toml) | Dependencies (`flwr`, `ollama`), run config and the `supergrid` federation |

## Setup

On **every** machine that will run a SuperNode:

```bash
ollama pull llama3.2:latest
ollama serve   # if not already running as a service
```

Then, from this directory:

```bash
pip install -e .
```

## Run

Start the SuperLink and SuperNodes as described in the
[top-level README](../README.md#running-the-grid), then:

```bash
flwr run . supergrid --stream
```

## Config

Set in `[tool.flwr.app.config]` in [pyproject.toml](pyproject.toml):

| Key | Default | Meaning |
|---|---|---|
| `model` | `llama3.2:latest` | Ollama model; must be pulled on every SuperNode |
| `prompt` | `In one sentence, what is federated learning?` | Prompt sent to all nodes |

Override at runtime:

```bash
flwr run . supergrid --run-config 'prompt="Explain SuperGrid in one line" model="llama3.2:latest"'
```
