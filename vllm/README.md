# vllm

SuperGrid LLM inference where each SuperNode calls a
local [vLLM](https://docs.vllm.ai) OpenAI-compatible server. See the
[top-level README](../README.md) for the architecture and message flow.

## Setup

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/) (`brew install uv`).

### 1. Environment

Create the `vllm_env` virtual environment in the **parent folder** (the repo root,
hence the `../`), not inside this one. `flwr run` bundles this folder, and a venv
inside it makes the bundle fail. From this directory:

```bash
uv venv --python 3.12 ../vllm_env
source ../vllm_env/bin/activate
uv pip install -r requirements.txt   # flwr, openai client, vllm (Linux only)
uv pip install -e .                  # this app
```

**Keep `vllm_env` activated** in every terminal that runs Flower commands. 

Check with `flwr --version` (expect 1.40.x).

### 2. Model server

vLLM is installed in `vllm_env` (via `requirements.txt` on Linux). It runs
as its own process, separate from the Flower app, and must be installed on
**every** SuperNode machine. Keep a server running on each (separate terminal, `vllm_env` activated):

```bash
vllm serve Qwen/Qwen2.5-0.5B-Instruct --port 8000
```

> **macOS (Apple Silicon):** upstream vLLM has no macOS wheels, so
> `requirements.txt` skips it there and you shouldn't build it from source. Use [vLLM-Metal](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/),
> the Apple Silicon (MLX/Metal) backend, following its install steps. It serves
> MLX models, e.g. `mlx-community/Qwen2.5-0.5B-Instruct-4bit`; set `model` in
> [pyproject.toml](pyproject.toml) to match what you serve.

### 3. Quick test: join nodes to the grid

This checks the grid itself (SuperLink + 2 SuperNodes) before the model server
is involved. Use one terminal per command, each with `vllm_env` activated.

1. **SuperLink** (once, on the hub machine). It serves the
   Fleet, Control and Runtime APIs together on a single HTTP port. Its default,
   `8000`, is also vLLM's default, so use another port (`9000` here):

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

- [ ] **vLLM server** running on every SuperNode machine and serving the model.
  Check: `curl -s http://127.0.0.1:8000/v1/models`; the model you passed to `vllm serve` must be listed and match `model` in `pyproject.toml`.
- [ ] **SuperLink** running (`flower-superlink --insecure --port 9000`).
  Check: it logs that it is listening, and `flwr config ls` shows the
  `selfhosted` connection.
- [ ] **SuperNodes registered**: one `flower-supernode` per node, each logging
  a `SuperNode ID`. Check: `flwr supernode list selfhosted` shows all of them
  `online`.
- [ ] **Flower app installed** in `vllm_env` (`uv pip install -e .`). There is no
  compile step: `flwr run` bundles this folder and uploads it. Check:
  `uv pip show supergrid-vllm`.
- [ ] **`vllm_env` activated** in the terminal where you run `flwr run`, and you are
  in this folder (the one containing `pyproject.toml`).

## Run

With the grid from the quick test running and `vllm serve` up on each
SuperNode, from this directory:

```bash
flwr run . selfhosted --stream
```

This is a small model arena. Each SuperNode receives the whole `prompts` list in
a single message, runs the prompts one after another and returns the result of
each. The ServerApp then compares the nodes in a table per prompt, followed by
a per-node summary. Example output (the numbers are illustrative, not measurements):

```text
=== Prompt 2/3 [reasoning] ===
A bat and a ball cost 1.10 pounds in total. ...

node id              model                       latency (s)  tokens  tokens/s  response
-------------------  --------------------------  -----------  ------  --------  ----------------------------------------------------------------------
9051407112396313730  Qwen/Qwen2.5-0.5B-Instruct  2.10         118     56.2      Let the ball cost x. Then the bat costs x + 1.00, so 2x + 1.00 = 1.1...
6656541696358605279  Qwen/Qwen2.5-0.5B-Instruct  3.40         121     35.6      The ball costs 5 pence. If the ball is 5p, the bat is 1.05, which to...
2217405577318429003  -                           -            -       -         NO REPLY before the 120 s timeout

Round trip 9.20 s for all 3 prompts; slowest node computed for 5.50 s (about 3.70 s Flower relay overhead)

=== Per-node summary (successful replies only) ===
node id               prompts  mean latency (s)  mean tokens/s
9051407112396313730         3              1.82           58.4
6656541696358605279         3              2.95           37.9
```

Rows are sorted by tokens/s, fastest first. A node that returned an error is
marked `FAILED` with the reason, and a node that did not reply before
`reply-timeout` is marked `NO REPLY`.

Override config at runtime, e.g.:

```bash
flwr run . selfhosted --stream --run-config 'prompt="{YOUR PROMPT}" prompts="" max-tokens=64'
```

### Choosing the model per node

The model is resolved on each SuperNode in this order: the `model` key in its
`--node-config` (e.g. `--node-config 'partition-id=0 model="Qwen/Qwen2.5-0.5B-Instruct"'`),
then `model` in the run config, then the first model the local vLLM server
lists. This lets nodes serving different models compete in the same arena.

## Config

Set in `[tool.flwr.app.config]` in [pyproject.toml](pyproject.toml):

| Key | Default | Meaning |
|---|---|---|
| `model` | `Qwen/Qwen2.5-0.5B-Instruct` | Model name; must match what `vllm serve` loaded. Empty means use the server's first model. A node's `--node-config` overrides it |
| `vllm-url` | `http://127.0.0.1:8000/v1` | Base URL of the node-local vLLM server |
| `max-tokens` | `128` | Max tokens generated per reply |
| `reply-timeout` | `120` | Seconds to wait for each node's reply to the **whole batch**, so one dead node cannot stall the run. Raise it as you add prompts or `max-tokens` |
| `prompts` | three prompts (factual, reasoning, translation) | JSON list of `{"id": "...", "prompt": "..."}` objects; `id` is optional and defaults to the 1-based position |
| `prompt` | `In one sentence, what is federated learning?` | Fallback: used as a single prompt with id `single` when `prompts` is empty or missing |

**Why is the list a JSON string?** Flower's run config only supports scalar
values (bool, int, float, str), not TOML arrays or tables. So `prompts` is a
JSON array stored in a TOML multi-line string, and the ServerApp parses it with
`json.loads`. Bad JSON, an empty list or an item without a string `prompt`
stops the run with a clear error.

### Limits

- **Broadcast only:** every prompt goes to every node. There is no routing or
  load balancing yet (see [TODO.md](../TODO.md)).
- **No streaming:** a reply arrives whole, so there is no time to first token.
- **One batch per node:** a node runs its prompts sequentially so per-prompt
  latencies stay comparable, and the grid is crossed once however many prompts
  there are. The cost is that nothing is printed until every node has finished
  (or `reply-timeout` passes), and a node that times out loses all of its
  results. A single failing prompt is reported on its own row, not the whole node.
- **Bounded by the slowest node:** the round trip lasts until the last node
  finishes its batch.
- **tokens/s is end to end:** it is completion tokens divided by the whole
  request time, so it includes prompt processing and not only decoding. Compare
  it between nodes, not against vLLM's own decode-speed figures.
- **Flower polling adds latency:** the Grid collects replies by polling every
  3 seconds (in flwr 1.40), so the round trip is rounded up to that step and
  the "relay overhead" figure includes it. Keep `reply-timeout` well above
  3 seconds: a shorter value can mark a node that has already answered as
  `NO REPLY`.
- **Temperature is 0** so output is as repeatable as the backend allows.

## Tests

The tests use fakes, so they need no vLLM server or running grid. With
`vllm_env` activated, from this directory:

```bash
uv pip install pytest
pytest tests
```

## Clean up

When you are done, from the top of this list down:

1. **Stop the processes** with `Ctrl+C` in each terminal: the SuperNodes first,
   then the SuperLink, then the model server.
   `vllm serve` holds GPU memory until it exits; confirm with `nvidia-smi`
   that no `vllm` process remains.
2. **Leave the environment:** `deactivate`. To delete it entirely (from this
   folder), `rm -rf ../vllm_env`; recreate it from the Setup section any time.
3. **Remove Flower's leftovers** (all safe to delete, recreated on demand):
   - `~/.flwr/runtime-envs/`: one throwaway environment per `flwr run`.
   - `.flwr/` in this folder: local run state.
   - The `[superlink.selfhosted]` entry in `~/.flwr/config.toml`, if you no
     longer need the connection.
4. **Free disk space from models** (optional, these are large):
   - Downloaded weights are cached in `~/.cache/huggingface/hub/`; delete the
     model folders you no longer need.
