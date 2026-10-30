"""Answer judge for agent runs, through `claude -p` (subscription, no tools).

The judge sees the question, the reference answer and one candidate answer; it never sees which arm produced
the answer. Verdicts go to `judgments.jsonl` next to `runs.jsonl`, keyed by question and arm, and resume
like runs do.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from subforest.eval.agent import Invoke, load_runs, run_claude
from subforest.eval.datasets import Dataset

Verdict = Literal["correct", "partial", "incorrect"]
VERDICTS: tuple[Verdict, ...] = ("correct", "partial", "incorrect")

JUDGE_PROMPT = """\
You grade answers to questions about documents. You get a question, a reference answer written by an expert
who read the document, and a candidate answer. Decide whether the candidate answers the question correctly.

- correct: it states the key facts of the reference (wording, length and extra detail do not matter) and
  does not contradict it.
- partial: it gets part of the key facts right but misses or garbles an important part.
- incorrect: it is wrong, contradicts the reference, misses the key facts, or says the documents do not
  cover a question that the reference does answer.

The reference may be terse (a list of names, a number, "Yes" or "No"). For a yes/no reference, the candidate
must reach the same yes or no. If the reference says "Unanswerable", the candidate is correct when it says the
documents do not answer the question, and incorrect when it gives a confident answer.

Reply with one JSON object and nothing else: {"verdict": "correct" | "partial" | "incorrect", "reason": "<one
short sentence>"}"""

_JSON = re.compile(r"\{.*\}", re.DOTALL)
_LIMIT = re.compile(
    r"usage limit|rate limit|limit reached|limit will reset|out of extra usage", re.IGNORECASE
)


def judge_input(question: str, reference: str, candidate: str) -> str:
    """The user message sent to the judge.

    Example:
        >>> print(judge_input("Q?", "R.", "C."))
        Question: Q?
        <BLANKLINE>
        Reference answer: R.
        <BLANKLINE>
        Candidate answer: C.
    """
    return f"Question: {question}\n\nReference answer: {reference}\n\nCandidate answer: {candidate}"


def judge_command(model: str, message: str, claude: str = "claude") -> list[str]:
    """The `claude -p` command line for one verdict: no tools, no MCP servers, JSON output.

    Example:
        >>> cmd = judge_command("haiku", "x")
        >>> cmd[:3], cmd[cmd.index("--tools") + 1], "--strict-mcp-config" in cmd
        (['claude', '-p', 'x'], '', True)
    """
    return [
        claude,
        "-p",
        message,
        "--model",
        model,
        "--tools",
        "",
        "--strict-mcp-config",
        "--system-prompt",
        JUDGE_PROMPT,
        "--output-format",
        "json",
        "--no-session-persistence",
    ]


def parse_verdict(text: str) -> tuple[Verdict | None, str]:
    """Pull the verdict and reason out of the judge's reply; `None` if it is unusable.

    Example:
        >>> parse_verdict('Sure: {"verdict": "partial", "reason": "Misses the second step."}')
        ('partial', 'Misses the second step.')
        >>> parse_verdict("no json")[0] is None
        True
    """
    match = _JSON.search(text)
    if not match:
        return None, text[:200]
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None, text[:200]
    verdict = data.get("verdict")
    return (verdict if verdict in VERDICTS else None), str(data.get("reason", ""))


def load_judgments(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Read `judgments.jsonl`, keyed by (question id, arm); later lines win."""
    if not path.exists():
        return {}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            out[(record["id"], record["arm"])] = record
    return out


def judge_runs(
    dataset: Dataset,
    runs_dir: Path,
    *,
    model: str = "haiku",
    max_runs: int | None = None,
    invoke: Invoke = run_claude,
    echo: Callable[[str], None] = print,
) -> int:
    """Judge every finished run without a verdict; returns how many were judged.

    Stops early, without error, when the subscription's usage limit is reached.
    """
    questions = {q.id: q for q in dataset.questions()}
    path = runs_dir / "judgments.jsonl"
    done = {k for k, v in load_judgments(path).items() if v["verdict"] is not None}
    todo: Sequence[dict[str, Any]] = [
        r
        for r in load_runs(runs_dir / "runs.jsonl")
        if r["status"] == "ok" and (r["id"], r["arm"]) not in done and r["id"] in questions
    ][:max_runs]
    for i, run in enumerate(todo, 1):
        q = questions[run["id"]]
        stdout = invoke(judge_command(model, judge_input(q.question, q.answer, run["answer"])), runs_dir)
        try:
            out: dict[str, Any] = json.loads(stdout)
        except json.JSONDecodeError:
            out = {"is_error": True, "result": stdout[-2000:]}
        reply = str(out.get("result") or "")
        if out.get("is_error") and _LIMIT.search(reply):
            echo(f"usage limit reached after {i - 1} verdicts; rerun later to resume")
            return i - 1
        verdict, reason = parse_verdict(reply) if not out.get("is_error") else (None, reply[:200])
        record = {"id": run["id"], "arm": run["arm"], "judge": model, "verdict": verdict, "reason": reason}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        echo(f"[{i}/{len(todo)}] {run['id']} {run['arm']}: {verdict}")
    return len(todo)
