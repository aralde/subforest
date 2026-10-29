import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client
from test_eval_offline import wixqa  # noqa: F401

from subforest import TreeStore
from subforest.cli import main
from subforest.eval import Dataset
from subforest.eval.agent import AgentConfig, agent_report, load_runs, run_agent, sign_test
from subforest.mcp import create_server
from subforest.retrievers import FTS5Retriever
from subforest.tools import Toolkit


def fake_claude(answers: dict[str, str], *, limit_after: int | None = None):  # type: ignore[no-untyped-def]
    """Stand-in for `claude -p`: runs the real toolkit like an agent (search, read) and logs calls."""
    seen: list[list[str]] = []

    def invoke(cmd: list[str], cwd: Path) -> str:
        seen.append(cmd)
        if limit_after is not None and len(seen) > limit_after:
            return json.dumps({"is_error": True, "result": "Claude AI usage limit reached|1761800000"})
        server = json.loads(Path(cmd[cmd.index("--mcp-config") + 1]).read_text())["mcpServers"]["docs"]
        args = server["args"]
        db, view, log = (
            args[args.index("--db") + 1],
            args[args.index("--view") + 1],
            args[args.index("--log") + 1],
        )
        question = cmd[2]
        with TreeStore(db) as store:
            toolkit = Toolkit(store, FTS5Retriever(store), view=view, budget_tokens=60)
            found = toolkit.call("search", query=question)
            target = found.data["hits"][0]["node"]
            if view == "tree":
                doc = next(n for n in found.data["nodes"] if store.get_node(int(n[1:])).kind == "doc")
                target = doc
            read = toolkit.call("read", node_id=target)
        with open(log, "a", encoding="utf-8") as f:
            for i, (tool, call_args, result) in enumerate(
                [("search", {"query": question}, found), ("read", {"node_id": target}, read)], 1
            ):
                f.write(
                    json.dumps({"call": i, "tool": tool, "args": call_args, **result.model_dump()}) + "\n"
                )
        return json.dumps(
            {
                "is_error": False,
                "result": answers.get(view, "I do not know."),
                "num_turns": 3,
                "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 20},
                "total_cost_usd": 0.001,
            }
        )

    invoke.seen = seen  # type: ignore[attr-defined]
    return invoke


def test_run_agent_records_both_arms_and_resumes(wixqa: Dataset, tmp_path: Path) -> None:  # noqa: F811
    out = tmp_path / "runs"
    invoke = fake_claude({"tree": "Up to 3 business days.", "chunks": "Not sure."})
    assert run_agent(wixqa, out, config=AgentConfig(), invoke=invoke, echo=lambda _: None) == 4
    runs = load_runs(out / "runs.jsonl")
    assert {(r["id"], r["arm"]) for r in runs} == {
        (q.id, a) for q in wixqa.questions() for a in ("chunks", "subforest")
    }
    first = invoke.seen[0]
    assert first[first.index("--tools") + 1] == "" and "--strict-mcp-config" in first
    assert all(r["calls"][1]["tool"] == "read" and r["input_tokens"] == 100 for r in runs)

    assert run_agent(wixqa, out, config=AgentConfig(), invoke=invoke, echo=lambda _: None) == 0
    assert len(invoke.seen) == 4

    report = agent_report(wixqa, runs)
    assert report.questions == 2
    sub, chunks = report.arms["subforest"], report.arms["chunks"]
    assert all(sub.gold_text) and sub.f1[0] > chunks.f1[0]
    text = report.markdown()
    assert "| Saw gold-doc text |" in text and "sign test" in text


def test_usage_limit_stops_without_recording(wixqa: Dataset, tmp_path: Path) -> None:  # noqa: F811
    out = tmp_path / "runs"
    messages: list[str] = []
    invoke = fake_claude({}, limit_after=1)
    assert run_agent(wixqa, out, config=AgentConfig(), invoke=invoke, echo=messages.append) == 1
    assert len(load_runs(out / "runs.jsonl")) == 1
    assert "usage limit reached after 1 runs" in messages[-1]


def test_cli_dry_run_and_report(wixqa: Dataset, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: F811
    out = tmp_path / "runs"
    root = str(wixqa.root)
    assert (
        main(["agent", "run", "wixqa", "--root", root, "--out", str(out), "--dry-run", "--limit", "1"]) == 0
    )
    printed = capsys.readouterr().out
    assert printed.startswith("2 runs pending") and "--model haiku" in printed
    assert main(["agent", "report", "wixqa", "--root", root, "--runs", str(out)]) == 2

    run_agent(wixqa, out, config=AgentConfig(), invoke=fake_claude({}), echo=lambda _: None)
    assert main(["agent", "report", "wixqa", "--root", root, "--runs", str(out), "--out", str(tmp_path)]) == 0
    assert (tmp_path / "wixqa-agent.md").read_text().startswith("# Agent runs — wixqa")


def test_server_logs_calls_caps_them_and_serves_chunks_view(corpus_dir: Path, tmp_path: Path) -> None:
    from subforest.build import build_corpus

    log = tmp_path / "calls.jsonl"
    with TreeStore() as store:
        build_corpus(corpus_dir, corpus_id="docs").write(store)
        toolkit = Toolkit(store, FTS5Retriever(store), view="chunks", budget_tokens=200)

        async def scenario() -> list[Any]:
            async with Client(create_server(toolkit, log=log, max_calls=2)) as client:
                names = sorted(t.name for t in (await client.list_tools()).tools)
                assert names == ["read", "search"]
                return [
                    await client.call_tool("search", {"query": "rotate token"}),
                    await client.call_tool("read", {"node_id": "n30"}),
                    await client.call_tool("search", {"query": "token"}),
                ]

        found, read, refused = anyio.run(scenario)
    text = found.content[0].text
    assert "Rotating tokens [n" in text and "●" not in text
    assert not read.is_error and refused.is_error and "budget of 2 calls" in refused.content[0].text
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert [(e["call"], e["tool"], e["blocked"]) for e in entries] == [
        (1, "search", False),
        (2, "read", False),
        (3, "search", True),
    ]


def test_sign_test_symmetry() -> None:
    assert sign_test(3, 12) == sign_test(12, 3)
