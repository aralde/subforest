"""Budgeted text rendering of a `SubForest` (what the agent sees after `search`)."""

from __future__ import annotations

from collections.abc import Callable

from subforest.models import Node, SubForest
from subforest.tokens import estimate_tokens

MAX_DOTS = 5


class _View:
    def __init__(self, forest: SubForest) -> None:
        self.forest = forest
        self.nodes = forest.nodes
        self.children: dict[int, list[int]] = {i: [] for i in self.nodes}
        for node in sorted(self.nodes.values(), key=lambda n: (n.order, n.id)):
            if node.parent_id is not None and node.parent_id in self.nodes:
                self.children[node.parent_id].append(node.id)
        self.hits: dict[int, int] = {}
        self.score: dict[int, float] = {}
        for root in forest.roots:
            self._aggregate(root)
        self.shown = set(self.nodes)
        self.dropped_docs = 0

    def _aggregate(self, node_id: int) -> None:
        hits = self.forest.hit_marks.get(node_id, 0)
        score = self.forest.scores.get(node_id, 0.0)
        for child in self.children[node_id]:
            self._aggregate(child)
            hits += self.hits[child]
            score += self.score[child]
        self.hits[node_id] = hits
        self.score[node_id] = score

    def doc_of(self, node_id: int) -> int | None:
        node: Node | None = self.nodes[node_id]
        while node is not None and node.kind != "doc":
            node = self.nodes.get(node.parent_id) if node.parent_id is not None else None
        return node.id if node else None

    def remove(self, node_id: int) -> None:
        stack = [node_id]
        while stack:
            current = stack.pop()
            self.shown.discard(current)
            stack.extend(self.children[current])
        parent = self.nodes[node_id].parent_id
        while parent is not None and self.nodes[parent].kind in ("dir", "site"):
            if any(c in self.shown for c in self.children[parent]) or parent in self.forest.roots:
                break
            self.shown.discard(parent)
            parent = self.nodes[parent].parent_id

    def text(self) -> str:
        lines: list[str] = []
        for root in self.forest.roots:
            if root in self.shown:
                self._lines(root, 0, lines)
        if self.dropped_docs:
            s = "" if self.dropped_docs == 1 else "s"
            lines.append(
                f"… {self.dropped_docs} more doc{s} with weaker hits (call search with more_results=true)"
            )
        return "\n".join(lines)

    def _lines(self, node_id: int, depth: int, out: list[str]) -> None:
        node = self.nodes[node_id]
        pad = "  " * depth
        if node.kind == "site":
            out.append(f"{pad}{node.title} (site)")
        else:
            line = f"{pad}{node.title} [{node.short_id}]"
            hits = self.hits[node_id]
            if hits and node.kind in ("doc", "section"):
                line += f" {'●' * min(hits, MAX_DOTS)} {hits} hit{'' if hits == 1 else 's'}"
            out.append(line)
        visible = [c for c in self.children[node_id] if c in self.shown]
        for child in visible:
            self._lines(child, depth + 1, out)
        hidden = self.forest.child_counts.get(node_id, len(self.children[node_id])) - len(visible)
        if hidden > 0:
            label = "more" if node.kind in ("site", "dir") else "section" if hidden == 1 else "sections"
            out.append(f"{pad}  … +{hidden} {label}")


def render(forest: SubForest, budget_tokens: int, estimator: Callable[[str], int] | None = None) -> str:
    """Render `forest` as an indented outline that fits `budget_tokens`, collapsing instead of truncating.

    Every node keeps its short id; doc and section lines carry their subtree hit count, and children
    outside the view are summarized as `… +N`. When over budget, the renderer first collapses the
    weakest leaf sections (keeping at least one per doc), then drops whole docs from weakest to strongest
    (reported in a footer), then collapses the strongest doc's remaining sections. If even the single
    strongest doc does not fit, that minimal view is returned anyway.

    Example:
        >>> root = Node(id=1, corpus_id="c", kind="site", title="docs/")
        >>> doc = Node(id=2, corpus_id="c", parent_id=1, kind="doc", title="Auth")
        >>> forest = SubForest(roots=[1], nodes={1: root, 2: doc}, hit_marks={2: 2}, child_counts={1: 3})
        >>> print(render(forest, 50))
        docs/ (site)
          Auth [n2] ●● 2 hits
          … +2 more
    """
    count = estimator or estimate_tokens
    view = _View(forest)

    def fits() -> bool:
        return count(view.text()) <= budget_tokens

    def weakness(node_id: int) -> tuple[float, int, int]:
        return (view.score[node_id], view.hits[node_id], -node_id)

    def leaf_sections() -> list[int]:
        return [
            i
            for i in view.shown
            if view.nodes[i].kind == "section" and not any(c in view.shown for c in view.children[i])
        ]

    while not fits():
        per_doc: dict[int | None, int] = {}
        for i in view.shown:
            if view.nodes[i].kind == "section":
                d = view.doc_of(i)
                per_doc[d] = per_doc.get(d, 0) + 1
        candidates = [i for i in leaf_sections() if per_doc[view.doc_of(i)] > 1]
        if not candidates:
            break
        view.remove(min(candidates, key=weakness))

    docs = sorted((i for i in view.shown if view.nodes[i].kind == "doc"), key=weakness)
    while not fits() and len(docs) > 1:
        view.remove(docs.pop(0))
        view.dropped_docs += 1

    while not fits():
        candidates = leaf_sections()
        if not candidates:
            break
        view.remove(min(candidates, key=weakness))

    return view.text()
