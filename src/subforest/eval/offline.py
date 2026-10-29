"""Tier 1 (scale) and tier 2 (evidence coverage) evaluations: no LLM involved."""

from __future__ import annotations

import hashlib
import statistics
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from subforest.build import BuildResult
from subforest.eval.datasets import Dataset, Question, build_qasper, build_wixqa, shown_node_ids
from subforest.induce import induce
from subforest.models import Node
from subforest.retrievers import FTS5Retriever
from subforest.store import TreeStore
from subforest.tokens import estimate_tokens

BUILDERS: dict[str, Callable[[Dataset], tuple[BuildResult, list[Question]]]] = {
    "wixqa": build_wixqa,
    "qasper": build_qasper,
}


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def _db_digest(path: Path) -> str:
    with TreeStore(path) as store:
        digest = hashlib.sha256()
        for line in store.connection.iterdump():
            digest.update(line.encode())
        return digest.hexdigest()


@dataclass
class BenchReport:
    """Scale numbers for one dataset."""

    dataset: str
    docs: int
    nodes: int
    chunks: int
    build_seconds: float
    db_mb: float
    deterministic: bool
    queries: int
    latency_ms: dict[str, dict[str, float]] = field(default_factory=dict)

    def markdown(self) -> str:
        """Render as a Markdown report.

        Example:
            >>> print(BenchReport("x", 1, 2, 3, 0.5, 0.1, True, 0).markdown().splitlines()[0])
            # Bench — x
        """
        lines = [
            f"# Bench — {self.dataset}",
            "",
            "| Docs | Nodes | Chunks | Build (s) | DB (MB) | Deterministic |",
            "|---|---|---|---|---|---|",
            f"| {self.docs:,} | {self.nodes:,} | {self.chunks:,} | {self.build_seconds:.1f} "
            f"| {self.db_mb:.1f} | {'yes' if self.deterministic else '**no**'} |",
            "",
            f"Latency over {self.queries} dataset questions (ms):",
            "",
            "| Step | p50 | p95 | max |",
            "|---|---|---|---|",
        ]
        for step, stats in self.latency_ms.items():
            lines.append(f"| {step} | {stats['p50']:.1f} | {stats['p95']:.1f} | {stats['max']:.1f} |")
        return "\n".join(lines) + "\n"


def bench(dataset: Dataset, *, queries: int = 200, k: int = 50, budget: int = 400) -> BenchReport:
    """Build the dataset twice (timing the second, comparing both), then time search / induce / render.

    Requires the raw files from `subforest data fetch`.
    """
    builder = BUILDERS[dataset.name]
    with tempfile.TemporaryDirectory() as tmp:
        digests = []
        for i in range(2):
            path = Path(tmp) / f"build{i}.db"
            start = time.perf_counter()
            result, questions = builder(dataset)
            with TreeStore(path) as store:
                result.write(store)
                FTS5Retriever(store)
            elapsed = time.perf_counter() - start
            digests.append(_db_digest(path))
        size_mb = path.stat().st_size / 1e6

    timings: dict[str, list[float]] = {"search": [], "induce": [], "render": []}
    with TreeStore(dataset.db) as store:
        retriever = FTS5Retriever(store)
        for q in questions[:queries]:
            t0 = time.perf_counter()
            hits = retriever.search(q.question, k=k)
            t1 = time.perf_counter()
            forest = induce(store, hits)
            t2 = time.perf_counter()
            forest.render(budget)
            t3 = time.perf_counter()
            for step, dt in zip(timings, (t1 - t0, t2 - t1, t3 - t2), strict=True):
                timings[step].append(dt * 1000)
    latency = {
        step: {"p50": statistics.median(v), "p95": _percentile(v, 0.95), "max": max(v)}
        for step, v in timings.items()
        if v
    }
    return BenchReport(
        dataset=dataset.name,
        docs=sum(n.kind == "doc" for n in result.nodes),
        nodes=len(result.nodes),
        chunks=len(result.chunks),
        build_seconds=elapsed,
        db_mb=size_mb,
        deterministic=digests[0] == digests[1],
        queries=min(queries, len(questions)),
        latency_ms=latency,
    )


class _Tree:
    def __init__(self, store: TreeStore) -> None:
        rows = store.connection.execute("SELECT id FROM nodes").fetchall()
        self.nodes: dict[int, Node] = {}
        for (node_id,) in rows:
            self.nodes[node_id] = store.get_node(node_id)
        self.children: dict[int, list[int]] = {}
        for node in self.nodes.values():
            if node.parent_id is not None:
                self.children.setdefault(node.parent_id, []).append(node.id)

    def doc_of(self, node_id: int) -> int | None:
        node: Node | None = self.nodes[node_id]
        while node is not None and node.kind != "doc":
            node = self.nodes.get(node.parent_id) if node.parent_id is not None else None
        return node.id if node else None

    def path_to(self, doc_id: int, offset: int) -> list[int]:
        """Node ids from the doc down to the deepest section whose span contains `offset`."""
        path = [doc_id]
        current = doc_id
        while True:
            nxt = next(
                (
                    c
                    for c in self.children.get(current, [])
                    if (span := self.nodes[c].span) is not None and span[0] <= offset < span[1]
                ),
                None,
            )
            if nxt is None:
                return path
            path.append(nxt)
            current = nxt


@dataclass
class _Arm:
    doc: int = 0
    evidence: int = 0
    tokens: list[int] = field(default_factory=list)


@dataclass
class CoverageReport:
    """Evidence coverage per budget for the `chunks` and `subforest` first views."""

    dataset: str
    questions: int
    with_spans: int
    k: int
    read_tokens: int
    mode: str
    budgets: list[int]
    arms: dict[str, dict[int, _Arm]]

    def rate(self, arm: str, budget: int, what: str) -> float:
        """Share of questions covered (0 to 1); `what` is `doc` or `evidence`."""
        total = self.questions if what == "doc" else self.with_spans
        return getattr(self.arms[arm][budget], what) / total if total else 0.0

    def markdown(self) -> str:
        """Render as a Markdown report with one row per budget."""
        lines = [
            f"# Evidence coverage — {self.dataset}",
            "",
            f"{self.questions} questions ({self.with_spans} with located evidence spans), "
            f"BM25 top-{self.k} hits, query mode `{self.mode}`.",
            "",
            "- **Gold doc**: the first view shows a chunk of (chunks) or a line for (subforest) "
            "a gold document.",
            "- **Evidence**: chunks: a shown chunk overlaps a gold evidence span; subforest: a shown node "
            f"contains the evidence and fits one `read` (≤ {self.read_tokens} tokens).",
            "",
            "| Budget (tokens) | Gold doc: chunks | Gold doc: subforest | Evidence: chunks "
            "| Evidence: subforest | Tokens used: chunks / subforest |",
            "|---|---|---|---|---|---|",
        ]
        for b in self.budgets:
            used = [
                statistics.mean(self.arms[a][b].tokens) if self.arms[a][b].tokens else 0 for a in self.arms
            ]
            evidence = (
                f"{self.rate('chunks', b, 'evidence'):.1%} | {self.rate('subforest', b, 'evidence'):.1%}"
                if self.with_spans
                else "n/a | n/a"
            )
            lines.append(
                f"| {b} | {self.rate('chunks', b, 'doc'):.1%} | {self.rate('subforest', b, 'doc'):.1%} | "
                f"{evidence} | {used[0]:.0f} / {used[1]:.0f} |"
            )
        return "\n".join(lines) + "\n"


def coverage(
    dataset: Dataset,
    *,
    budgets: Sequence[int] = (250, 500, 1000, 2000),
    k: int = 50,
    read_tokens: int = 800,
    limit: int | None = None,
    mode: str = "raw",
) -> CoverageReport:
    """Compare what the agent's first view contains under each token budget, for both arms.

    `mode="titled"` prefixes each question with its context (the paper title for QASPER), since QASPER
    questions are written against one paper and are often ambiguous across the whole corpus.
    """
    questions = dataset.questions()[:limit]
    arms: dict[str, dict[int, _Arm]] = {a: {b: _Arm() for b in budgets} for a in ("chunks", "subforest")}
    with TreeStore(dataset.db) as store:
        tree = _Tree(store)
        retriever = FTS5Retriever(store)
        texts: dict[int, str] = {}
        for q in questions:
            query = f"{q.context}: {q.question}" if mode == "titled" and q.context else q.question
            hits = retriever.search(query, k=k)
            gold_docs = set(q.gold_docs)
            reachable: set[int] = set()
            for span in q.gold_spans:
                if span.doc not in texts:
                    texts[span.doc] = store.doc_text(span.doc) or ""
                for node_id in tree.path_to(span.doc, span.start):
                    node_span = tree.nodes[node_id].span
                    if (
                        node_span
                        and estimate_tokens(texts[span.doc][node_span[0] : node_span[1]]) <= read_tokens
                    ):
                        reachable.add(node_id)

            shown_chunks = []
            for hit in hits:
                row = store.connection.execute(
                    'SELECT text, start, "end" FROM chunks WHERE id = ?', (hit.chunk_id,)
                ).fetchone()
                node = tree.nodes[hit.node_id]
                cost = estimate_tokens(f"{node.title} [{node.short_id}]\n{row[0]}\n")
                shown_chunks.append((tree.doc_of(hit.node_id), row[1], row[2], cost))

            forest = induce(store, hits) if hits else None
            for b in budgets:
                used, seen = 0, []
                for doc, start, end, cost in shown_chunks:
                    if used + cost > b:
                        break
                    used += cost
                    seen.append((doc, start, end))
                arm = arms["chunks"][b]
                arm.tokens.append(used)
                arm.doc += any(d in gold_docs for d, _, _ in seen)
                arm.evidence += any(
                    d == s.doc and start < s.end and s.start < end
                    for d, start, end in seen
                    for s in q.gold_spans
                )

                text = forest.render(b) if forest else ""
                ids = shown_node_ids(text)
                arm = arms["subforest"][b]
                arm.tokens.append(estimate_tokens(text))
                arm.doc += bool(ids & gold_docs)
                arm.evidence += bool(ids & reachable)
    return CoverageReport(
        dataset=dataset.name,
        questions=len(questions),
        with_spans=sum(1 for q in questions if q.gold_spans),
        k=k,
        read_tokens=read_tokens,
        mode=mode,
        budgets=list(budgets),
        arms=arms,
    )
