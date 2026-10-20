# ollama

SuperGrid LLM inference where each SuperNode calls a locally-served
[Ollama](https://ollama.com) model. See the [top-level README](../README.md)
for the architecture and message flow.

| File | Purpose |
|---|---|
| [supergrid_llm/server_app.py](supergrid_llm/server_app.py) | `ServerApp`: fans the prompt out to every SuperNode and prints replies |
| [supergrid_llm/client_app.py](supergrid_llm/client_app.py) | `ClientApp`: `@app.query()` handler that calls `ollama.generate` |
| [pyproject.toml](pyproject.toml) | Dependencies (`flwr`, `ollama`), run config |
| [requirements.txt](requirements.txt) | What to install into `ollama_env` |

## Setup

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/) (`brew install uv`).

### 1. Environment

Create the `ollama_env` virtual environment in the **parent folder** (the repo root,
hence the `../`), not inside this one. `flwr run` bundles this folder, and a venv
inside it makes the bundle fail. From this directory:

```bash
uv venv --python 3.12 ../ollama_env
source ../ollama_env/bin/activate
uv pip install -r requirements.txt   # flwr + ollama client
uv pip install -e .                  # this app
```

**Keep `ollama_env` activated** in every terminal that runs Flower commands. The
SuperLink and SuperNodes launch helper processes (such as `flower-superexec`)
by name, and fail with `No such file or directory: 'flower-superexec'` if the
venv's `bin/` is not on `PATH`. Check with `flwr --version` (expect 1.40.x).

### 2. Model server

Ollama is a system app, not a pip package, so it lives outside `ollama_env`.
Install it on **every** machine that will run a SuperNode (`brew install ollama`
or the installer from [ollama.com](https://ollama.com)), then:

```bash
ollama pull llama3.2:latest
ollama serve   # if not already running as a service
```

### 3. Quick test: join nodes to the grid

This checks the grid itself (SuperLink + 2 SuperNodes) before the model server
is involved. Use one terminal per command, each with `ollama_env` activated.

1. **SuperLink** (once, on the hub machine). It serves the
   Fleet, Control and Runtime APIs together on a single HTTP port. Its default is
   `8000`; this guide uses `9000`:

   ```bash
   flower-superlink --insecure --port 9000
   ```

   For SuperNodes on other machines, also bind it to a reachable address with
   `--host` (see `flower-superlink --help`).

2. **SuperNode 1**. Point `--superlink` at the SuperLink (`127.0.0.1:9000` if
   everything runs on one machine). `--port` is this SuperNode's own local
   API port (default `9094`):

   ```bash
   flower-supernode --insecure \
     --superlink <superlink-host>:9000 \
     --port 9094 \
     --node-config "partition-id=0"
   ```

3. **SuperNode 2**, on another machine or terminal. SuperNodes on the same
   machine need different `--port` values:

   ```bash
   flower-supernode --insecure \
     --superlink <superlink-host>:9000 \
     --port 9095 \
     --node-config "partition-id=1"
   ```

4. **Register the SuperLink for the CLI.** `flwr run` and `flwr supernode list`
   find the SuperLink through a named *connection* in `~/.flwr/config.toml`
   (created on first use). Add one for your SuperLink. The built-in `supergrid`
   connection is Flower's hosted service, so use a different name:

   ```toml
   [superlink.selfhosted]
   address = "127.0.0.1:9000"
   insecure = true
   ```

   Check it with `flwr config ls`.

5. **Check the nodes joined.** Both SuperNodes should log a `SuperNode ID`.
   List them from the SuperLink. On a separate terminal run: 

   ```bash
   flwr supernode list selfhosted
   ```

   Both should show `online`. You should get something like:
```bash

Using SuperLink: selfhosted (127.0.0.1:9000)
📄 Listing all nodes...
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃       Node ID       ┃ Owner ┃ Status ┃ Elapsed ┃   Status Changed @   ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ 6032684002794125263 │ none  │ online │ 3m 33s  │ 2026-10-20 16:43:07Z │
├─────────────────────┼───────┼────────┼─────────┼──────────────────────┤
│ 9622216904661572043 │ none  │ online │ 78s     │ 2026-10-20 16:45:22Z │
└─────────────────────┴───────┴────────┴─────────┴──────────────────────┘
```
If a node doesn't show up, check the `--superlink` address, that port `9000`
is reachable, and that SuperNodes on the same machine have unique `--port` values.
Leave the grid running for the next step.

## Checklist before you run

Everything below must be up, each in its own terminal where needed:

- [ ] **Ollama** running on every SuperNode machine and serving the model.
  Check: `curl -s http://127.0.0.1:11434/api/tags`; the model (`llama3.2:latest` by default) must be listed.
- [ ] **SuperLink** running (`flower-superlink --insecure --port 9000`).
  Check: it logs that it is listening, and `flwr config ls` shows the
  `selfhosted` connection.
- [ ] **SuperNodes registered**: one `flower-supernode` per node, each logging
  a `SuperNode ID`. Check: `flwr supernode list selfhosted` shows all of them
  `online`.
- [ ] **Flower app installed** in `ollama_env` (`uv pip install -e .`). There is no
  compile step: `flwr run` bundles this folder and uploads it. Check:
  `uv pip show supergrid-llm`.
- [ ] **`ollama_env` activated** in the terminal where you run `flwr run`, and you are
  in this folder (the one containing `pyproject.toml`).

## Run

With the grid from the quick test running, from this directory:

```bash
flwr run . selfhosted --stream
```

Expected: the connected SuperNode IDs, then one generated response per node.
If a node fails (for example the model isn't pulled), the ServerApp prints
`Node <id> failed: ...`.

## Config

Set in `[tool.flwr.app.config]` in [pyproject.toml](pyproject.toml):

| Key | Default | Meaning |
|---|---|---|
| `model` | `llama3.2:latest` | Ollama model; must be pulled on every SuperNode |
| `prompt` | `In one sentence, what is federated learning?` | Prompt sent to all nodes |

Override at runtime:

```bash
flwr run . selfhosted --run-config 'prompt="{YOUR PROMPT}"'
```

## Clean up

When you are done, from the top of this list down:

1. **Stop the processes** with `Ctrl+C` in each terminal: the SuperNodes first,
   then the SuperLink, then the model server.
   Stop Ollama too if you started it yourself (`ollama stop llama3.2:latest`
   unloads the model; `brew services stop ollama` stops a background service).
2. **Leave the environment:** `deactivate`. To delete it entirely (from this
   folder), `rm -rf ../ollama_env`; recreate it from the Setup section any time.
3. **Remove Flower's leftovers** (all safe to delete, recreated on demand):
   - `~/.flwr/runtime-envs/`: one throwaway environment per `flwr run`.
   - `.flwr/` in this folder: local run state.
   - The `[superlink.selfhosted]` entry in `~/.flwr/config.toml`, if you no
     longer need the connection.
4. **Free disk space from models** (optional, these are large):
   - `ollama rm llama3.2:latest` removes a pulled model; `ollama list` shows
     what is installed.
