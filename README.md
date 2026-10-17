# inference_supergrid

Experiments with LLM inference on a [Flower](https://flower.ai) SuperGrid: one
SuperLink plus N SuperNodes. A `ServerApp` sends the same prompt to every
SuperNode; each SuperNode runs it through a **locally-served** LLM backend and
sends the response back. Only prompt/response text crosses the grid — no
weights, no data.

Each backend lives in its own folder with its own README, dependencies and
config. They share the same grid and message protocol.

| Folder | Backend | Docs |
|---|---|---|
| [ollama/](ollama/) | [Ollama](https://ollama.com) | [README](ollama/README.md), [TESTING](ollama/TESTING.md) |
| [vllm/](vllm/) | [vLLM](https://docs.vllm.ai) (OpenAI-compatible server) | [README](vllm/README.md) |

Tested with `flwr==1.23.0` (SuperLink/SuperNode deployment API).

## Architecture

```mermaid
flowchart TB
    CLI["flwr run . supergrid"]

    subgraph SuperLink["SuperLink — insecure :9092 (Fleet API) / :9093 (Control API)"]
        SA["flwr-serverapp<br/>server_app.py — uses Grid to reach every SuperNode"]
    end

    subgraph Node1["SuperNode 1"]
        CA1["flwr-clientapp<br/>client_app.py — @app.query()"]
        B1["Local LLM backend<br/>(Ollama / vLLM / ...)"]
        CA1 <--> B1
    end

    subgraph Node2["SuperNode 2"]
        CA2["flwr-clientapp<br/>client_app.py — @app.query()"]
        B2["Local LLM backend<br/>(Ollama / vLLM / ...)"]
        CA2 <--> B2
    end

    CLI -- "submit run" --> SuperLink
    SA <-- "Fleet API :9092" --> CA1
    SA <-- "Fleet API :9092" --> CA2
```

Only the prompt goes out and the generated text comes back over the grid —
each SuperNode's model, and any local data, stays on that node. The only
backend-specific code is `client_app.py`; `server_app.py` is identical.

## Message flow

```mermaid
sequenceDiagram
    actor You
    participant CLI as flwr run
    participant SL as SuperLink
    participant SA as ServerApp (Grid)
    participant N1 as SuperNode 1 (ClientApp)
    participant N2 as SuperNode 2 (ClientApp)
    participant B1 as LLM backend (node 1)
    participant B2 as LLM backend (node 2)

    You->>CLI: flwr run . supergrid --stream
    CLI->>SL: submit app
    SL->>SA: start ServerApp process
    SA->>SL: grid.get_node_ids()
    SL-->>SA: [node1_id, node2_id]

    par SuperNode 1
        SA->>N1: Message(type=QUERY, prompt)
        N1->>B1: generate(model, prompt)
        B1-->>N1: generated text
        N1-->>SA: Message(reply, response)
    and SuperNode 2
        SA->>N2: Message(type=QUERY, prompt)
        N2->>B2: generate(model, prompt)
        B2-->>N2: generated text
        N2-->>SA: Message(reply, response)
    end

    SA->>SA: print each node's response
```

## Running the grid

Backend setup (installing the model server, pulling models, `pip install -e .`)
is described in each folder's README. The grid itself is started the same way
for every backend. From the backend folder, in separate terminals:

1. **SuperLink** (once, on the hub machine):

   ```bash
   flower-superlink --insecure
   ```

2. **SuperNode 1** (point `--superlink` at the SuperLink's Fleet API, port `9092`):

   ```bash
   flower-supernode --insecure \
     --superlink <superlink-host>:9092 \
     --clientappio-api-address 127.0.0.1:9094 \
     --node-config "partition-id=0"
   ```

3. **SuperNode 2**, on another machine or terminal. Each SuperNode needs its
   own `--clientappio-api-address`:

   ```bash
   flower-supernode --insecure \
     --superlink <superlink-host>:9092 \
     --clientappio-api-address 127.0.0.1:9095 \
     --node-config "partition-id=1"
   ```

4. **Run the app** against the `supergrid` federation defined in the folder's
   `pyproject.toml`:

   ```bash
   flwr run . supergrid --stream
   ```

   (On very new `flwr` releases the federation address may instead need to be
   defined in `~/.flwr/config.toml` — check `flwr run --help`.)

The ServerApp prints the connected SuperNode IDs, followed by each node's
response. Config such as `prompt` and `model` lives in
`[tool.flwr.app.config]` in each `pyproject.toml` and can be overridden with
`--run-config`; the available keys are listed in each folder's README.
