# TODO

Roadmap from the current stateless "same prompt to every node" demo toward an
orchestrated inference grid. The first part is what the **demo** needs; the
second part is what can wait.

Demo goal: a user sends a prompt to an HTTP API on the hub; the hub starts the
right model on the right node if needed, routes the prompt, and returns the
answer, with node health visible.

## Demo scope (in order)

- [ ] **0. Spike: can a blocking `ServerApp` serve an API?** Start a trivial
  FastAPI server inside `main()` and check that the run stays up and that the
  `Grid` works from there. Everything below assumes yes. Fallback if not: a
  separate gateway process in front of the SuperLink.
- [ ] **1. Node command protocol.** Turn the `ClientApp` into a small command
  handler: an `action` field (`start`, `status`, `generate`, `stop`) in the
  existing query config. This is the base for items 2-5, so build it once.
  - `generate` carries a full chat request (`messages`, `temperature`,
    `max_tokens`, as a JSON string in the `ConfigRecord`), with a timeout on
    the backend call and a message TTL long enough for slow generations.
  - A small backend interface (`start`, `status`, `generate`, `stop`) so the
    `ollama/` and `vllm/` folders speak the same protocol.
  - Per-node values (model, port) come from `--node-config`, not `run_config`,
    which is identical for every node.
- [ ] **2. API interface on the server.** HTTP endpoint (e.g. OpenAI-style
  `/v1/chat/completions`) so users send prompts to the server instead of a
  prompt fixed in `pyproject.toml`. One dispatcher thread owns the `Grid`;
  HTTP handlers put requests on a queue and wait for the reply, because
  `Grid` thread-safety is unverified.
- [ ] **3. Orchestrator-launched model backends.** The server sends `start`
  and the node launches the backend itself, so nothing needs downloading or
  serving beforehand.
  - vLLM: `vllm serve` detached (`Popen(..., start_new_session=True)`),
    returns immediately; the server polls `status` until ready.
  - Ollama: `start` is an `ollama pull` against the running daemon.
  - Idempotent: check the backend's `/v1/models` first; keep PID and port in a
    file on the node, since the `ClientApp` is rebuilt per message.
  - Security: a node only launches models from an allowlist in its own
    `--node-config`; the server never sends command-line arguments.
- [ ] **4. Routing, including specialised models.** A simple rule choosing the
  node for a prompt: first round-robin among ready nodes, then by model. Run
  domain models (e.g. finance, healthcare) on different nodes and pick by an
  explicit `model` field in the request. These two are one feature: routing by
  model is the rule, round-robin is the fallback among nodes serving the same
  model. (A classifier that chooses the domain automatically comes later.)
- [ ] **5. Health checks and basic metrics.** `status` returns ready / not
  ready plus, for vLLM, running requests, waiting requests and KV-cache usage
  read from its local `/metrics` (match metric names by prefix; they change
  between versions). The orchestrator polls on a timer and exposes a
  `/health`-style view. Routing in item 4 only considers ready nodes.
- [ ] **6. Least-outstanding-requests balancing.** Replace round-robin with
  "send to the ready node with the fewest in-flight requests", using the
  counters the dispatcher already has and the polled metrics from item 5. This
  is the "load balancing" part of the demo; it is a small step on top of 4 and 5.

## Later (not needed for the demo)

- [ ] **Session tracking.** Everything is stateless. Decide where history
  lives (gateway vs node) and whether a session is pinned to a node. For the
  demo the client can resend the full `messages` list each time, which the
  chat request format in item 1 already supports.
- [ ] **Scale-out / scale-in from metrics.** Add or remove nodes and models
  automatically from the item 5 metrics. The demo only balances across nodes
  that are already running.
- [ ] **Automatic domain classifier** for specialised-model routing.
- [ ] **Merge the two `server_app.py` files** into one shared module once the
  gateway exists (they are identical today).
- [ ] **TLS and auth.** Insecure mode is fine on localhost only. Needed before
  nodes launch processes on request over a real network.

## Open questions

- **Streaming.** Flower messages are request/reply, so there are no token
  streams. Either return buffered replies (simplest, fine for the demo), or
  use Flower only as the control plane (`start`, `status`, metrics, routing)
  and let the gateway call each node's backend endpoint directly for
  generation. The second gives streaming and lower latency but means prompts no
  longer cross only the grid, which the README currently advertises.
- **Capability advertising.** How a node tells the orchestrator which model and
  hardware it has. `--node-config` is the starting point.
- **Apple Silicon.** Upstream vLLM has no macOS wheels; local testing of the
  vLLM path on a Mac needs vLLM-Metal, so the Ollama backend is the practical
  way to exercise the protocol until a Linux node is available.
