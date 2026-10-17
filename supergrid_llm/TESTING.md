# Testing the SuperGrid LLM base example

A step-by-step guide to run the `supergrid_llm` example on a single machine
(1 SuperLink + 2 SuperNodes + Ollama) and understand how each piece works.
Everything is done with [`uv`](https://docs.astral.sh/uv/).

## What you will test

A `ServerApp` sends the same prompt to every SuperNode on the grid. Each
SuperNode's `ClientApp` calls its local Ollama model and returns the text.
Only prompt/response text crosses the grid. See [the top-level README](../README.md) for the
architecture and sequence diagrams.

| Component | Command | Port | Code |
|---|---|---|---|
| SuperLink | `flower-superlink` | 9092 (Fleet), 9093 (Control), 9091 (ServerAppIO) | — |
| SuperNode 1 | `flower-supernode` | ClientAppIO 9094 | [client_app.py](supergrid_llm/client_app.py) |
| SuperNode 2 | `flower-supernode` | ClientAppIO 9095 | [client_app.py](supergrid_llm/client_app.py) |
| ServerApp | started by SuperLink on `flwr run` | — | [server_app.py](supergrid_llm/server_app.py) |
| Ollama | `ollama serve` | 11434 | — |

## 1. Prerequisites

- `uv` installed (`brew install uv`)
- Ollama installed (`brew install ollama`) — https://ollama.com
- ~3 GB free disk for `llama3.2`

```bash
uv --version
ollama --version
```

## 2. Create the environment and install dependencies

Run from the example directory:

```bash
cd supergrid_llm

# Fresh venv with a pinned Python (Flower 1.23 works well on 3.10–3.12)
uv venv --python 3.11 .venv
source .venv/bin/activate

# Install the app (editable) + its deps: flwr>=1.13,<1.24 and ollama
uv pip install -e .
```

> A `.venv` may already exist in this directory (created with Python 3.9 from
> conda). If you hit odd import/version errors, remove it and recreate it:
> `rm -rf .venv && uv venv --python 3.11 .venv`.

Alternative without activating: prefix commands with `uv run` (e.g.
`uv run flower-superlink --insecure`). That also syncs deps from
`pyproject.toml` automatically.

Verify:

```bash
flwr --version              # expect 1.23.x
python -c "import flwr, ollama; print(flwr.__version__)"
which flower-superlink flower-supernode
```

## 3. Prepare Ollama

```bash
ollama serve &              # skip if the Ollama app/service is already running
ollama pull llama3.2:latest
```

Sanity check the model works *before* involving Flower:

```bash
ollama run llama3.2:latest "Say hi in five words"
curl -s localhost:11434/api/tags | head
```

The model name must match `model` in `[tool.flwr.app.config]` in
[pyproject.toml](pyproject.toml).

## 4. Start the grid (4 terminals)

Activate the venv (`source .venv/bin/activate`) in each one, from
`supergrid_llm/`.

**Terminal 1 — SuperLink**

```bash
flower-superlink --insecure
```

Look for it listening on `9092` (Fleet) and `9093` (Control).

**Terminal 2 — SuperNode 1**

```bash
flower-supernode --insecure \
  --superlink 127.0.0.1:9092 \
  --clientappio-api-address 127.0.0.1:9094 \
  --node-config "partition-id=0"
```

**Terminal 3 — SuperNode 2** (must use a different ClientAppIO port)

```bash
flower-supernode --insecure \
  --superlink 127.0.0.1:9092 \
  --clientappio-api-address 127.0.0.1:9095 \
  --node-config "partition-id=1"
```

Both SuperNodes should log that they connected/registered with the SuperLink.

## 5. Run the app

**Terminal 4**

```bash
flwr run . supergrid --stream
```

`supergrid` is the federation defined in [pyproject.toml](pyproject.toml)
(`address = "127.0.0.1:9093"`, `insecure = true`). `--stream` follows the
ServerApp logs live.

### Expected output

```
Connected SuperNodes: [<id1>, <id2>]

--- Node <id1> ---
Federated learning is ...

--- Node <id2> ---
Federated learning is ...
```

Two different node IDs with a generated sentence each means the whole path
worked: CLI → SuperLink → ServerApp → Fleet API → ClientApp → Ollama → back.

## 6. Experiments to understand how it works

1. **Change the prompt / model at runtime**
   ```bash
   flwr run . supergrid --stream \
     --run-config 'prompt="Explain SuperGrid in one line" model="llama3.2:latest"'
   ```
2. **Follow the message path.** In [server_app.py](supergrid_llm/server_app.py)
   `grid.get_node_ids()` discovers nodes and `grid.send_and_receive()` fans out
   one `QUERY` message per node. In
   [client_app.py](supergrid_llm/client_app.py) `@app.query()` handles it. Add
   a `print(context.node_id, context.node_config)` in `query()` and re-run to
   see which node handled what (and the `partition-id` you passed).
3. **Different models per node.** Pull a second model (`ollama pull qwen2.5:0.5b`)
   and make `query()` pick the model from `context.node_config` (e.g. via
   `partition-id`) instead of `run_config` — shows how per-node config differs
   from per-run config.
4. **Node failure.** Stop SuperNode 2 (Ctrl+C) and re-run: the ServerApp sees
   one node. Stop Ollama and re-run: the reply has an error and the server
   prints `Node <id> failed: ...` (the `reply.has_error()` branch).
5. **Add a third node.** Start another SuperNode with
   `--clientappio-api-address 127.0.0.1:9096 --node-config "partition-id=2"`;
   the server picks it up with no code change.
6. **Multi-machine.** Run the SuperLink on one host and point
   `--superlink <host>:9092` from SuperNodes on other machines (each needs
   Ollama + the model + this app installed). Open ports 9092/9093 as needed.

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Connected SuperNodes: []` | SuperNodes not started or can't reach `:9092`; check their logs and `--superlink` address. |
| `flwr run` rejects `supergrid` federation | Newer `flwr` may want it in `~/.flwr/config.toml`; check `flwr run --help`. Ensure `flwr<1.24` is installed. |
| Address already in use (9094/9095) | Each SuperNode needs a unique `--clientappio-api-address`; kill stale processes (`lsof -i :9094`). |
| `ollama._types.ResponseError: model not found` | `ollama pull <model>` on **every** SuperNode machine; name must match `model` config. |
| `ConnectionError` to Ollama | `ollama serve` not running; check `curl localhost:11434`. |
| `ModuleNotFoundError: supergrid_llm` in a node | App not installed in the venv used by that SuperNode: `uv pip install -e .`. |
| Old code still running after edits | Restart the SuperNodes (they spawn ClientApp from the installed package). |

## 8. Clean up

```bash
# Ctrl+C in the SuperLink and SuperNode terminals, then:
deactivate
pkill -f flower-s  # optional: any leftover flower processes
```

Flower state lives in `~/.flwr/` — safe to delete to reset the SuperLink
database.
