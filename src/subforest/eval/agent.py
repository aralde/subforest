"""Tier 3: agent runs over one dataset, `chunks` vs `subforest` arms, through `claude -p` (subscription).

Each run starts a fresh `claude -p` whose only tools come from `subforest serve`, which logs each call.
Results go to `runs.jsonl` (one line per question and arm) so an interrupted run resumes where it stopped.
Metrics need no LLM judge: whether the agent saw text from a gold document (a chunk in a chunks search, or a
`read`), whether a gold document appeared at all, and token F1 against the reference answer.
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from subforest.eval.datasets import Dataset, Question, shown_node_ids
from subforest.store import TreeStore
from subforest.tools import ToolError, parse_node_id

Arm = Literal["chunks", "subforest"]
ARMS: tuple[Arm, ...] = ("chunks", "subforest")

SYSTEM_PROMPT = """\
You answer questions about {corpus} using only the documentation tools you are given.
Use at most {max_calls} tool calls. Base the answer on what you read, and say so if the docs do not cover it.
Give a concise answer in plain text."""

_LIMIT = re.compile(
    r"usage limit|rate limit|limit reached|limit will reset|out of extra usage", re.IGNORECASE
)
_WORD = re.compile(r"\w+")
_STOP = frozenset(
    ["a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is", "are", "be", "it", "this", "that"]
)

Invoke = Callable[[list[str], Path], str]


@dataclass
class AgentConfig:
    """How each run is set up; both arms share everything except the view."""

    model: str = "haiku"
    max_calls: int = 10
    budget_tokens: int = 800
    corpus: str = "the Wix help center"
    claude: str = "claude"
    python: str = sys.executable


def token_f1(prediction: str, reference: str) -> float:
    """Bag-of-words F1 between two texts, ignoring case, punctuation and a few stop words.

    Example:
        >>> round(token_f1("Go to Settings, then Payments.", "Open Settings and click Payments"), 2)
        0.5
    """
    pred = Counter(w for w in _WORD.findall(prediction.lower()) if w not in _STOP)
    ref = Counter(w for w in _WORD.findall(reference.lower()) if w not in _STOP)
    overlap = sum((pred & ref).values())
    if not overlap:
        return 0.0
    precision, recall = overlap / sum(pred.values()), overlap / sum(ref.values())
    return 2 * precision * recall / (precision + recall)


def claude_command(config: AgentConfig, arm: Arm, mcp_config: Path, question: str) -> list[str]:
    """The `claude -p` command line for one run: no built-in tools, only the `docs` MCP server.

    Example:
        >>> cmd = claude_command(AgentConfig(), "chunks", Path("m.json"), "How?")
        >>> cmd[:3], "--strict-mcp-config" in cmd, cmd[cmd.index("--tools") + 1]
        (['claude', '-p', 'How?'], True, '')
    """
    system = SYSTEM_PROMPT.format(corpus=config.corpus, max_calls=config.max_calls)
    return [
        config.claude,
        "-p",
        question,
        "--model",
        config.model,
        "--tools",
        "",
        "--strict-mcp-config",
        "--mcp-config",
        str(mcp_config),
        "--allowedTools",
        "mcp__docs",
        "--system-prompt",
        system,
        "--output-format",
        "json",
        "--no-session-persistence",
    ]


def mcp_config(config: AgentConfig, arm: Arm, db: Path, log: Path) -> dict[str, Any]:
    """MCP config that serves `db` in the arm's view, logging calls to `log` and capping them.

    Example:
        >>> server = mcp_config(AgentConfig(python="py"), "chunks", Path("c.db"), Path("l"))["mcpServers"]
        >>> args = server["docs"]["args"]
        >>> args[args.index("--view") + 1]
        'chunks'
    """
    view = "chunks" if arm == "chunks" else "tree"
    args = ["-m", "subforest.cli", "serve", "--db", str(db), "--view", view]
    args += ["--budget", str(config.budget_tokens), "--max-calls", str(config.max_calls), "--log", str(log)]
    return {"mcpServers": {"docs": {"command": config.python, "args": args}}}


def run_claude(cmd: list[str], cwd: Path) -> str:  # pragma: no cover - needs the claude CLI
    """Run one `claude -p` command and return its stdout."""
    done = subprocess.run(
        cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600, check=False
    )
    return done.stdout or json.dumps({"is_error": True, "result": done.stderr.strip()[-2000:]})


class UsageLimitReached(Exception):
    """The subscription's usage window is spent; rerun later and the runner resumes."""


def run_one(
    question: Question, arm: Arm, db: Path, config: AgentConfig, invoke: Invoke = run_claude
) -> dict[str, Any]:
    """Run one question in one arm and return the record written to `runs.jsonl`."""
    with tempfile.TemporaryDirectory(prefix="subforest-run-") as tmp:
        work = Path(tmp)
        log = work / "calls.jsonl"
        cfg = work / "mcp.json"
        cfg.write_text(json.dumps(mcp_config(config, arm, db, log)), encoding="utf-8")
        start = time.monotonic()
        stdout = invoke(claude_command(config, arm, cfg, question.question), work)
        elapsed = time.monotonic() - start
        calls = (
            [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            if log.exists()
            else []
        )
    try:
        out: dict[str, Any] = json.loads(stdout)
    except json.JSONDecodeError:
        out = {"is_error": True, "result": stdout[-2000:]}
    answer = str(out.get("result") or "")
    if out.get("is_error") and _LIMIT.search(answer):
        raise UsageLimitReached(answer)
    usage = out.get("usage") or {}
    return {
        "id": question.id,
        "arm": arm,
        "model": config.model,
        "status": "error" if out.get("is_error") else "ok",
        "answer": answer,
        "seconds": round(elapsed, 2),
        "turns": out.get("num_turns"),
        "input_tokens": sum(
            usage.get(k, 0)
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        ),
        "output_tokens": usage.get("output_tokens", 0),
        "cost_usd_equivalent": out.get("total_cost_usd"),
        "calls": [
            {
                "tool": c["tool"],
                "args": c["args"],
                "shown": sorted(shown_node_ids(c["text"])),
                "error": c["error"],
                "blocked": c["blocked"],
            }
            for c in calls
        ],
    }


def load_runs(path: Path) -> list[dict[str, Any]]:
    """Read `runs.jsonl`; a later line for the same question and arm replaces an earlier one."""
    if not path.exists():
        return []
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            latest[(record["id"], record["arm"])] = record
    return list(latest.values())


def pending(
    questions: Sequence[Question], arms: Iterable[Arm], done: Iterable[dict[str, Any]]
) -> list[tuple[Question, Arm]]:
    """(question, arm) pairs without an `ok` record, interleaving arms so a partial run stays paired.

    Example:
        >>> qs = [Question(id=i, question="?", answer="", gold_docs=[1]) for i in "ab"]
        >>> [(q.id, a) for q, a in pending(qs, ARMS, [{"id": "a", "arm": "chunks", "status": "ok"}])]
        [('a', 'subforest'), ('b', 'chunks'), ('b', 'subforest')]
    """
    finished = {(r["id"], r["arm"]) for r in done if r["status"] == "ok"}
    return [(q, a) for q in questions for a in arms if (q.id, a) not in finished]


def run_agent(
    dataset: Dataset,
    out: Path,
    *,
    config: AgentConfig,
    arms: Sequence[Arm] = ARMS,
    limit: int | None = None,
    max_runs: int | None = None,
    invoke: Invoke = run_claude,
    echo: Callable[[str], None] = print,
) -> int:
    """Run pending (question, arm) pairs, appending to `out/runs.jsonl`; returns how many ran.

    Stops early, without error, when the subscription's usage limit is reached.
    """
    out.mkdir(parents=True, exist_ok=True)
    runs_path = out / "runs.jsonl"
    todo = pending(dataset.questions()[:limit], arms, load_runs(runs_path))[:max_runs]
    for i, (question, arm) in enumerate(todo, 1):
        try:
            record = run_one(question, arm, dataset.db.resolve(), config, invoke)
        except UsageLimitReached as exc:
            echo(f"usage limit reached after {i - 1} runs; rerun later to resume ({exc})")
            return i - 1
        with runs_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        echo(f"[{i}/{len(todo)}] {question.id} {arm}: {record['status']}, {len(record['calls'])} calls")
    return len(todo)


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact sign test p-value over discordant pairs.

    Example:
        >>> round(sign_test(12, 3), 3), sign_test(0, 0)
        (0.035, 1.0)
    """
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / (1 << n)
    return min(1.0, 2 * tail)


def bootstrap_ci(diffs: Sequence[float], *, rounds: int = 5000, seed: int = 0) -> tuple[float, float]:
    """95% percentile bootstrap interval for the mean of paired differences (seeded, so reproducible).

    Example:
        >>> bootstrap_ci([1.0] * 10)
        (1.0, 1.0)
    """
    if not diffs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(rounds))
    return means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


@dataclass
class _ArmStats:
    gold_text: list[bool] = field(default_factory=list)
    gold_shown: list[bool] = field(default_factory=list)
    f1: list[float] = field(default_factory=list)
    calls: list[int] = field(default_factory=list)
    input_tokens: list[int] = field(default_factory=list)
    seconds: list[float] = field(default_factory=list)


def _doc_of(store: TreeStore, cache: dict[int, int | None], node_id: int) -> int | None:
    if node_id not in cache:
        try:
            node = store.get_node(node_id)
        except KeyError:
            cache[node_id] = None
        else:
            chain = [*store.ancestors(node_id), node]
            cache[node_id] = next((n.id for n in reversed(chain) if n.kind == "doc"), None)
    return cache[node_id]


def _read_id(call: dict[str, Any]) -> int | None:
    if call["tool"] != "read" or call["error"] or call["blocked"]:
        return None
    try:
        return parse_node_id(call["args"].get("node_id", ""))
    except ToolError:
        return None


@dataclass
class AgentReport:
    """Paired comparison of the two arms over questions that finished in both."""

    dataset: str
    model: str
    questions: int
    arms: dict[Arm, _ArmStats]

    def markdown(self) -> str:
        """Render as a Markdown report."""
        a, b = self.arms["chunks"], self.arms["subforest"]
        lines = [
            f"# Agent runs — {self.dataset}",
            "",
            f"{self.questions} questions answered in both arms by `{self.model}` through `claude -p`, "
            "same retriever (BM25), call budget and view budget. No LLM judge.",
            "",
            "- **Saw gold-doc text**: chunks: a gold-doc chunk was shown by search or a gold node was read; "
            "subforest: a gold node was read (outline lines alone do not count).",
            "- **Gold doc shown**: the gold doc's id appeared in any tool output.",
            "",
            "| Metric | chunks | subforest |",
            "|---|---|---|",
            f"| Saw gold-doc text | {statistics.fmean(a.gold_text):.1%} "
            f"| {statistics.fmean(b.gold_text):.1%} |",
            f"| Gold doc shown by any call | {statistics.fmean(a.gold_shown):.1%} "
            f"| {statistics.fmean(b.gold_shown):.1%} |",
            f"| Answer token F1 vs reference | {statistics.fmean(a.f1):.3f} | {statistics.fmean(b.f1):.3f} |",
            f"| Tool calls (mean) | {statistics.fmean(a.calls):.1f} | {statistics.fmean(b.calls):.1f} |",
            f"| Input tokens (mean) | {statistics.fmean(a.input_tokens):,.0f} "
            f"| {statistics.fmean(b.input_tokens):,.0f} |",
            f"| Seconds (median) | {statistics.median(a.seconds):.1f} | {statistics.median(b.seconds):.1f} |",
            "",
            "Paired differences (subforest - chunks), 95% bootstrap CI:",
            "",
            "| Metric | Δ | 95% CI | subforest only / chunks only | sign test p |",
            "|---|---|---|---|---|",
        ]
        for name, xs, ys in (
            ("Saw gold-doc text", a.gold_text, b.gold_text),
            ("Gold doc shown", a.gold_shown, b.gold_shown),
        ):
            diffs = [float(y) - float(x) for x, y in zip(xs, ys, strict=True)]
            wins = sum(y and not x for x, y in zip(xs, ys, strict=True))
            losses = sum(x and not y for x, y in zip(xs, ys, strict=True))
            lo, hi = bootstrap_ci(diffs)
            lines.append(
                f"| {name} | {statistics.fmean(diffs):+.1%} | {lo:+.1%} to {hi:+.1%} | {wins} / {losses} "
                f"| {sign_test(wins, losses):.3f} |"
            )
        f1_diffs = [y - x for x, y in zip(a.f1, b.f1, strict=True)]
        lo, hi = bootstrap_ci(f1_diffs)
        lines.append(f"| Answer token F1 | {statistics.fmean(f1_diffs):+.3f} | {lo:+.3f} to {hi:+.3f} | | |")
        return "\n".join(lines) + "\n"


def agent_report(dataset: Dataset, runs: Sequence[dict[str, Any]]) -> AgentReport:
    """Score `runs` against the dataset's gold docs and answers, keeping questions finished in both arms."""
    by_key = {(r["id"], r["arm"]): r for r in runs if r["status"] == "ok"}
    questions = [q for q in dataset.questions() if all((q.id, arm) in by_key for arm in ARMS)]
    arms = {arm: _ArmStats() for arm in ARMS}
    models = {r["model"] for r in by_key.values()}
    cache: dict[int, int | None] = {}
    with TreeStore(dataset.db) as store:
        for q in questions:
            gold = set(q.gold_docs)
            for arm in ARMS:
                run = by_key[(q.id, arm)]
                stats = arms[arm]
                read = {
                    d
                    for c in run["calls"]
                    if (i := _read_id(c)) is not None and (d := _doc_of(store, cache, i)) is not None
                }
                shown = {
                    d for c in run["calls"] for i in c["shown"] if (d := _doc_of(store, cache, i)) is not None
                }
                text_seen = read | (shown if arm == "chunks" else set())
                stats.gold_text.append(bool(text_seen & gold))
                stats.gold_shown.append(bool((shown | read) & gold))
                stats.f1.append(token_f1(run["answer"], q.answer))
                stats.calls.append(len(run["calls"]))
                stats.input_tokens.append(run["input_tokens"])
                stats.seconds.append(run["seconds"])
    return AgentReport(dataset.name, ", ".join(sorted(models)) or "n/a", len(questions), arms)
