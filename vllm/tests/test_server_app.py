import json
from types import SimpleNamespace

import pytest

from supergrid_vllm.server_app import (
    build_rows,
    format_table,
    load_prompts,
    parse_replies,
    snippet,
    unwrap_error,
)


def ctx(**run_config):
    return SimpleNamespace(run_config=run_config)


def test_valid_list():
    raw = json.dumps([{"id": "a", "prompt": "one"}, {"id": "b", "prompt": "two"}])
    assert load_prompts(ctx(prompts=raw, prompt="x")) == [
        {"id": "a", "prompt": "one"},
        {"id": "b", "prompt": "two"},
    ]


def test_missing_id_defaults_to_one_based_index():
    raw = json.dumps([{"prompt": "one"}, {"id": "named", "prompt": "two"}, {"prompt": "three"}])
    ids = [p["id"] for p in load_prompts(ctx(prompts=raw, prompt="x"))]
    assert ids == ["1", "named", "3"]


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_or_missing_falls_back_to_single_prompt(raw):
    config = {"prompt": "fallback"} if raw is None else {"prompts": raw, "prompt": "fallback"}
    assert load_prompts(ctx(**config)) == [{"id": "single", "prompt": "fallback"}]


def test_empty_list_is_rejected():
    with pytest.raises(ValueError, match="non-empty"):
        load_prompts(ctx(prompts="[]", prompt="x"))


def test_invalid_json_is_rejected():
    with pytest.raises(ValueError, match="not valid JSON"):
        load_prompts(ctx(prompts="[{oops", prompt="x"))


@pytest.mark.parametrize(
    "raw",
    ['{"prompt": "x"}', '["just a string"]', '[{"id": "a"}]', '[{"prompt": 5}]'],
)
def test_wrong_shape_is_rejected(raw):
    with pytest.raises(ValueError):
        load_prompts(ctx(prompts=raw, prompt="x"))


def fake_reply(node, error=None, results=None, compute_s=1.0):
    config = {} if results is None else {"results": json.dumps(results), "compute_s": compute_s}
    return SimpleNamespace(
        metadata=SimpleNamespace(src_node_id=node),
        has_error=lambda: error is not None,
        error=SimpleNamespace(reason=error),
        content={"config": config},
    )


def result(tps, text="hello\nworld"):
    return dict(
        response=text, model="m", latency_s=1.0, completion_tokens=10, tokens_per_s=tps
    )


def test_nodes_flag_failed_and_missing_nodes():
    replies = [fake_reply(1, results=[result(5.0)]), fake_reply(2, error="boom")]
    nodes = parse_replies([1, 2, 3], replies, expected=1)
    assert [n["status"] for n in nodes.values()] == ["OK", "FAILED", "NO REPLY"]


@pytest.mark.parametrize("results", [[], [result(1.0), result(2.0)]])
def test_wrong_number_of_results_marks_node_failed(results):
    nodes = parse_replies([1], [fake_reply(1, results=results)], expected=1)
    assert nodes[1]["status"] == "FAILED" and "bad reply" in nodes[1]["error"]


def test_reply_without_results_marks_node_failed():
    nodes = parse_replies([1], [fake_reply(1, results=None)], expected=1)
    assert nodes[1]["status"] == "FAILED"


def test_rows_pick_the_prompt_and_report_per_prompt_errors():
    replies = [
        fake_reply(1, results=[result(5.0), {"error": "ValueError: too long"}]),
        fake_reply(2, results=[result(9.0), result(3.0)]),
    ]
    nodes = parse_replies([1, 2], replies, expected=2)
    first = build_rows(nodes, 0)
    second = build_rows(nodes, 1)
    assert [r["tokens_per_s"] for r in first] == [5.0, 9.0]
    assert [r["status"] for r in second] == ["FAILED", "OK"]
    assert second[0]["error"] == "ValueError: too long"


def test_table_sorted_by_tokens_per_s_with_failures_last():
    replies = [
        fake_reply(1, results=[result(5.0)]),
        fake_reply(2, error="boom"),
        fake_reply(4, results=[result(9.0)]),
    ]
    nodes = parse_replies([1, 2, 3, 4], replies, expected=1)
    table = format_table(build_rows(nodes, 0), timeout=30)
    order = [line.split()[0] for line in table.splitlines()[2:]]
    assert order == ["4", "1", "2", "3"]
    assert "FAILED: boom" in table
    assert "NO REPLY before the 30 s timeout" in table


def test_snippet_collapses_newlines_and_truncates():
    assert snippet("a\n\nb   c") == "a b c"
    assert len(snippet("x" * 200)) == 70


def test_unwrap_error_strips_flower_wrapper_and_keeps_plain_text():
    wrapped = "<class 'RuntimeError'>:<'vLLM request to http://x/v1 failed (ConnectionError): refused'>"
    assert unwrap_error(wrapped) == "RuntimeError: vLLM request to http://x/v1 failed (ConnectionError): refused"
    assert unwrap_error("plain\ntext") == "plain text"
