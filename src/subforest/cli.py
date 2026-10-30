"""Command-line interface: build, search, serve, and the offline eval commands (data, bench, coverage)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from subforest.build import build_corpus
from subforest.eval import FETCHERS, Dataset, bench, coverage, data_root
from subforest.eval.agent import (
    ARMS,
    AgentConfig,
    agent_report,
    claude_command,
    load_runs,
    pending,
    prompt_for,
    run_agent,
    select_questions,
)
from subforest.eval.datasets import http_download
from subforest.induce import induce
from subforest.policy import Policy
from subforest.retrievers import FTS5Retriever
from subforest.store import TreeStore

CORPUS_NAMES = {"wixqa": "the Wix help center", "qasper": "a collection of NLP research papers"}


def _build(args: argparse.Namespace) -> int:
    source: Path = args.source
    db: Path = args.db
    if not source.exists():
        print(f"error: {source} does not exist", file=sys.stderr)
        return 2
    if db.exists():
        if not args.force:
            print(f"error: {db} already exists (use --force to replace it)", file=sys.stderr)
            return 2
        db.unlink()
    result = build_corpus(source, corpus_id=args.corpus_id, max_chunk_chars=args.max_chunk_chars)
    with TreeStore(db) as store:
        result.write(store)
        FTS5Retriever(store)
    docs = sum(n.kind == "doc" for n in result.nodes)
    print(f"built {db}: {len(result.nodes)} nodes, {docs} docs, {len(result.chunks)} chunks")
    return 0


def _search(args: argparse.Namespace) -> int:
    db: Path = args.db
    if not db.exists():
        print(f"error: {db} does not exist (run subforest build first)", file=sys.stderr)
        return 2
    with TreeStore(db) as store:
        hits = FTS5Retriever(store).search(args.query, k=args.k)
        if not hits:
            print("no hits")
            return 0
        print(induce(store, hits).render(args.budget))
    return 0


def _serve(args: argparse.Namespace) -> int:
    db: Path = args.db
    if not db.exists():
        print(f"error: {db} does not exist (run subforest build first)", file=sys.stderr)
        return 2
    try:
        from subforest.mcp import serve
    except ImportError:
        print("error: the MCP server needs the extra: pip install 'subforest[mcp]'", file=sys.stderr)
        return 2
    policy = Policy.load(args.policy) if args.policy else None
    serve(
        db,
        policy=policy,
        budget_tokens=args.budget,
        turn_idle_seconds=args.turn_idle_seconds,
        view=args.view,
        log=args.log,
        max_calls=args.max_calls,
    )
    return 0


def _dataset(args: argparse.Namespace) -> Dataset:
    return Dataset(args.dataset, args.root or data_root())


def _write_report(out: Path | None, name: str, text: str) -> None:
    print(text, end="")
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(text, encoding="utf-8")
        print(f"wrote {out / name}", file=sys.stderr)


def _data_fetch(args: argparse.Namespace) -> int:
    dataset = _dataset(args)
    FETCHERS[dataset.name](dataset, http_download)
    print(f"{dataset.name}: {dataset.db} and {dataset.questions_path} ({len(dataset.questions())} questions)")
    return 0


def _needs_fetch(dataset: Dataset) -> bool:
    if dataset.db.exists() and dataset.questions_path.exists():
        return False
    print(f"error: run `subforest data fetch {dataset.name}` first", file=sys.stderr)
    return True


def _bench(args: argparse.Namespace) -> int:
    dataset = _dataset(args)
    if _needs_fetch(dataset):
        return 2
    report = bench(dataset, queries=args.queries, k=args.k, budget=args.budget)
    _write_report(args.out, f"{dataset.name}-bench.md", report.markdown())
    return 0


def _coverage(args: argparse.Namespace) -> int:
    dataset = _dataset(args)
    if _needs_fetch(dataset):
        return 2
    report = coverage(dataset, budgets=args.budgets, k=args.k, limit=args.limit, mode=args.mode)
    suffix = "" if args.mode == "raw" else f"-{args.mode}"
    _write_report(args.out, f"{dataset.name}-coverage{suffix}.md", report.markdown())
    return 0


def _agent_run(args: argparse.Namespace) -> int:
    dataset = _dataset(args)
    if _needs_fetch(dataset):
        return 2
    config = AgentConfig(
        model=args.model,
        max_calls=args.max_calls,
        budget_tokens=args.budget,
        corpus=args.corpus or CORPUS_NAMES[dataset.name],
        mode=args.mode,
    )
    selection = {"evidence_only": args.evidence_only, "one_per_doc": args.one_per_doc}
    arms = ARMS if args.arm == "both" else (args.arm,)
    if args.dry_run:
        questions = select_questions(dataset.questions(), **selection)
        todo = pending(questions[: args.limit], arms, load_runs(args.out / "runs.jsonl"))
        todo = todo[: args.max_runs]
        print(f"{len(todo)} runs pending in {args.out}; first command:")
        if todo:
            prompt = prompt_for(todo[0][0], config.mode)
            print(" ".join(claude_command(config, todo[0][1], Path("mcp.json"), prompt)))
        return 0
    run_agent(
        dataset, args.out, config=config, arms=arms, limit=args.limit, max_runs=args.max_runs, **selection
    )
    return 0


def _agent_report(args: argparse.Namespace) -> int:
    dataset = _dataset(args)
    runs = load_runs(args.runs / "runs.jsonl")
    report = agent_report(dataset, runs)
    if not report.questions:
        print("error: no question has finished in both arms yet", file=sys.stderr)
        return 2
    _write_report(args.out, f"{dataset.name}-agent.md", report.markdown())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code.

    Example:
        >>> main(["build", "missing-dir", "--db", "x.db"])
        2
    """
    parser = argparse.ArgumentParser(prog="subforest")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build a tree database from Markdown files or a sitemap.xml")
    build.add_argument("source", type=Path, help="directory of Markdown files, or a local sitemap.xml")
    build.add_argument("--db", type=Path, required=True, help="SQLite file to create")
    build.add_argument("--corpus-id", help="corpus id (default: directory name)")
    build.add_argument("--max-chunk-chars", type=int, default=1000)
    build.add_argument("--force", action="store_true", help="replace --db if it exists")
    build.set_defaults(func=_build)
    search = sub.add_parser("search", help="search a built database and print the induced sub-forest")
    search.add_argument("query")
    search.add_argument("--db", type=Path, required=True, help="SQLite file created by subforest build")
    search.add_argument("-k", type=int, default=10, help="number of chunk hits to induce from")
    search.add_argument("--budget", type=int, default=400, help="token budget for the rendered view")
    search.set_defaults(func=_search)
    serve = sub.add_parser("serve", help="serve the agent tools as an MCP server over stdio")
    serve.add_argument("--db", type=Path, required=True, help="SQLite file created by subforest build")
    serve.add_argument("--policy", type=Path, help="tool-order policy (.yaml, .yml or .json)")
    serve.add_argument("--budget", type=int, default=400, help="token budget for search / expand views")
    serve.add_argument(
        "--turn-idle-seconds",
        type=float,
        default=120.0,
        help="a pause this long between calls starts a new policy turn",
    )
    serve.add_argument(
        "--view", choices=["tree", "chunks"], default="tree", help="chunks: flat baseline for evals"
    )
    serve.add_argument("--log", type=Path, help="append one JSON line per tool call to this file")
    serve.add_argument("--max-calls", type=int, help="answer at most this many tool calls, then refuse")
    serve.set_defaults(func=_serve)

    datasets = sorted(FETCHERS)
    data = sub.add_parser("data", help="download and build eval datasets (data never goes in the repo)")
    data_sub = data.add_subparsers(dest="data_command", required=True)
    fetch = data_sub.add_parser("fetch", help="download a dataset and build corpus.db + questions.jsonl")
    fetch.add_argument("dataset", choices=datasets)
    fetch.add_argument("--root", type=Path, help="data root (default: $SUBFOREST_DATA or ~/.cache/subforest)")
    fetch.set_defaults(func=_data_fetch)

    bench_p = sub.add_parser("bench", help="tier 1: build time, size, determinism and latency (no LLM)")
    bench_p.add_argument("dataset", choices=datasets)
    bench_p.add_argument("--root", type=Path)
    bench_p.add_argument("--queries", type=int, default=200)
    bench_p.add_argument("-k", type=int, default=50)
    bench_p.add_argument("--budget", type=int, default=400)
    bench_p.add_argument("--out", type=Path, help="directory to also write the Markdown report to")
    bench_p.set_defaults(func=_bench)

    cov = sub.add_parser(
        "coverage", help="tier 2: gold evidence in the first view, chunks vs subforest (no LLM)"
    )
    cov.add_argument("dataset", choices=datasets)
    cov.add_argument("--root", type=Path)
    cov.add_argument("--budgets", type=int, nargs="+", default=[250, 500, 1000, 2000])
    cov.add_argument("-k", type=int, default=50)
    cov.add_argument("--limit", type=int)
    cov.add_argument("--mode", choices=["raw", "titled"], default="raw")
    cov.add_argument("--out", type=Path)
    cov.set_defaults(func=_coverage)

    agent = sub.add_parser("agent", help="tier 3: agent runs through claude -p, chunks vs subforest")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    run = agent_sub.add_parser("run", help="run pending questions; resumes from runs.jsonl")
    run.add_argument("dataset", choices=datasets)
    run.add_argument("--root", type=Path)
    run.add_argument("--out", type=Path, required=True, help="directory holding runs.jsonl")
    run.add_argument("--arm", choices=["both", *ARMS], default="both")
    run.add_argument("--limit", type=int, help="only the first N questions")
    run.add_argument("--max-runs", type=int, help="stop after N runs in this invocation")
    run.add_argument("--model", default="haiku")
    run.add_argument("--max-calls", type=int, default=10)
    run.add_argument("--budget", type=int, default=800, help="token budget for search views, both arms")
    run.add_argument("--corpus", help="how the system prompt names the corpus (default: per dataset)")
    run.add_argument("--mode", choices=["raw", "titled"], default="raw", help="titled: name the source doc")
    run.add_argument("--evidence-only", action="store_true", help="only questions with located evidence")
    run.add_argument("--one-per-doc", action="store_true", help="only the first question per gold doc")
    run.add_argument("--dry-run", action="store_true", help="show what would run, call nothing")
    run.set_defaults(func=_agent_run)
    rep = agent_sub.add_parser("report", help="paired comparison of finished runs")
    rep.add_argument("dataset", choices=datasets)
    rep.add_argument("--root", type=Path)
    rep.add_argument("--runs", type=Path, required=True, help="directory holding runs.jsonl")
    rep.add_argument("--out", type=Path, help="directory to also write the Markdown report to")
    rep.set_defaults(func=_agent_report)
    args = parser.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
