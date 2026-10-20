"""ServerApp: run a list of prompts across every SuperNode and compare the replies.

Each node gets the whole prompt list in a single message and returns the results
for every prompt. The replies are printed as one table per prompt, sorted by
tokens per second, followed by a per-node summary.
"""

import json
import re
import time
from collections import defaultdict

from flwr.app import ConfigRecord, Context, Message, MessageType, RecordDict
from flwr.serverapp import Grid, ServerApp

app = ServerApp()

SNIPPET_CHARS = 70


def load_prompts(context: Context) -> list[dict]:
    """Read the prompt list from the run config.

    The run config only holds scalars, so `prompts` is a JSON string. Falls back
    to the single `prompt` key when `prompts` is empty or missing.
    """
    raw = context.run_config.get("prompts")
    if not raw or not str(raw).strip():
        return [{"id": "single", "prompt": str(context.run_config["prompt"])}]

    try:
        items = json.loads(str(raw))
    except json.JSONDecodeError as err:
        raise ValueError(f"`prompts` is not valid JSON: {err}") from err

    if not isinstance(items, list) or not items:
        raise ValueError("`prompts` must be a non-empty JSON list")

    prompts = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("prompt"), str):
            raise ValueError(
                f'`prompts` item {index} must be an object with a string "prompt"'
            )
        prompts.append({"id": str(item.get("id", index)), "prompt": item["prompt"]})
    return prompts


def snippet(text: str) -> str:
    """Collapse whitespace and cut to the first characters of a response."""
    flat = " ".join(text.split())
    return flat if len(flat) <= SNIPPET_CHARS else flat[: SNIPPET_CHARS - 3] + "..."


def unwrap_error(reason) -> str:
    """Strip Flower's "<class 'X'>:<'message'>" wrapper so the cause is readable."""
    text = " ".join(str(reason).split())
    match = re.fullmatch(r"<class '(\w+)'>:<'(.*)'>", text)
    return f"{match.group(1)}: {match.group(2)}" if match else text


def parse_replies(node_ids, replies, expected: int) -> dict:
    """One entry per node: its per-prompt results, or why there are none."""
    by_node = {reply.metadata.src_node_id: reply for reply in replies}
    nodes = {}
    for node_id in node_ids:
        reply = by_node.get(node_id)
        if reply is None:
            nodes[node_id] = {"status": "NO REPLY"}
        elif reply.has_error():
            nodes[node_id] = {"status": "FAILED", "error": reply.error.reason}
        else:
            config = reply.content["config"]
            try:
                results = json.loads(config["results"])
                if not isinstance(results, list) or len(results) != expected:
                    raise ValueError(f"expected {expected} results")
            except (KeyError, ValueError) as err:
                nodes[node_id] = {"status": "FAILED", "error": f"bad reply: {err}"}
                continue
            nodes[node_id] = {
                "status": "OK",
                "results": results,
                "compute_s": float(config["compute_s"]),
            }
    return nodes


def build_rows(nodes: dict, index: int) -> list[dict]:
    """One row per node for the prompt at `index`."""
    rows = []
    for node_id, node in nodes.items():
        if node["status"] != "OK":
            rows.append({"node": node_id, **node})
            continue
        result = node["results"][index]
        if "error" in result:
            rows.append({"node": node_id, "status": "FAILED", "error": result["error"]})
        else:
            rows.append({"node": node_id, "status": "OK", **result})
    return rows


def format_table(rows: list[dict], timeout: float) -> str:
    """Render rows as a text table, fastest first, with failures at the bottom."""
    ok = sorted(
        (r for r in rows if r["status"] == "OK"),
        key=lambda r: r["tokens_per_s"],
        reverse=True,
    )
    bad = [r for r in rows if r["status"] != "OK"]

    header = ("node id", "model", "latency (s)", "tokens", "tokens/s", "response")
    lines = [
        (
            str(r["node"]),
            r["model"],
            f"{r['latency_s']:.2f}",
            str(r["completion_tokens"]),
            f"{r['tokens_per_s']:.1f}",
            snippet(r["response"]),
        )
        for r in ok
    ]
    for r in bad:
        if r["status"] == "FAILED":
            detail = f"FAILED: {unwrap_error(r['error'])}"
        else:
            detail = f"NO REPLY before the {timeout:g} s timeout"
        lines.append((str(r["node"]), "-", "-", "-", "-", detail))

    widths = [max(len(row[i]) for row in [header, *lines]) for i in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in [header, ("-" * w for w in widths), *lines]
    )


@app.main()
def main(grid: Grid, context: Context) -> None:
    prompts = load_prompts(context)
    timeout = float(context.run_config.get("reply-timeout", 120))

    node_ids = list(grid.get_node_ids())
    print(f"Connected SuperNodes: {node_ids}")

    # One message per node carries every prompt, so the grid is crossed once.
    batch = json.dumps([item["prompt"] for item in prompts])
    messages = [
        Message(
            content=RecordDict({"config": ConfigRecord({"prompts": batch})}),
            message_type=MessageType.QUERY,
            dst_node_id=node_id,
            group_id="1",
        )
        for node_id in node_ids
    ]

    start = time.perf_counter()
    replies = list(grid.send_and_receive(messages, timeout=timeout))
    round_trip = time.perf_counter() - start

    nodes = parse_replies(node_ids, replies, expected=len(prompts))

    # Per-node latency and tokens/s across prompts, for the final summary.
    history = defaultdict(list)

    for index, item in enumerate(prompts):
        rows = build_rows(nodes, index)
        for row in rows:
            if row["status"] == "OK":
                history[row["node"]].append((row["latency_s"], row["tokens_per_s"]))

        print(f"\n=== Prompt {index + 1}/{len(prompts)} [{item['id']}] ===")
        print(item["prompt"])
        print()
        print(format_table(rows, timeout))

    compute = [n["compute_s"] for n in nodes.values() if n["status"] == "OK"]
    if compute:
        slowest = max(compute)
        print(
            f"\nRound trip {round_trip:.2f} s for all {len(prompts)} prompts; slowest node "
            f"computed for {slowest:.2f} s (about {round_trip - slowest:.2f} s Flower relay overhead)"
        )
    else:
        print(f"\nRound trip {round_trip:.2f} s; no successful replies")

    print("\n=== Per-node summary (successful replies only) ===")
    if not history:
        print("No successful replies.")
        return
    print("node id               prompts  mean latency (s)  mean tokens/s")
    for node_id, values in history.items():
        mean_latency = sum(v[0] for v in values) / len(values)
        mean_tps = sum(v[1] for v in values) / len(values)
        print(f"{node_id:<20}  {len(values):>7}  {mean_latency:>16.2f}  {mean_tps:>13.1f}")
