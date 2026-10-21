"""Core data model: nodes of the document tree, chunks of text, search hits and induced sub-forests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

NodeKind = Literal["site", "dir", "doc", "section"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Node(_Frozen):
    """A node in the document-structure tree (site, directory, document or section).

    `span` is the `(start, end)` character range inside the owning document, for sections and docs.

    Example:
        >>> Node(id=1, corpus_id="docs", kind="doc", title="Auth", path="guides/auth.md").parent_id is None
        True
    """

    id: int
    corpus_id: str
    parent_id: int | None = None
    kind: NodeKind
    title: str
    url: str | None = None
    path: str | None = None
    order: int = 0
    span: tuple[int, int] | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.parent_id == self.id:
            raise ValueError("a node cannot be its own parent")
        if self.span is not None and not 0 <= self.span[0] <= self.span[1]:
            raise ValueError(f"invalid span {self.span}")
        return self

    @property
    def short_id(self) -> str:
        """Stable short id shown to agents.

        Example:
            >>> Node(id=31, corpus_id="docs", kind="section", title="Tokens").short_id
            'n31'
        """
        return f"n{self.id}"


class Chunk(_Frozen):
    """A contiguous slice of text that belongs to exactly one node.

    Example:
        >>> Chunk(id=1, node_id=33, text="Tokens expire.", start=120, end=134).end
        134
    """

    id: int
    node_id: int
    text: str
    start: int
    end: int

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not 0 <= self.start <= self.end:
            raise ValueError(f"invalid chunk range ({self.start}, {self.end})")
        return self


class Hit(_Frozen):
    """One retrieval result: a chunk, the node that owns it, its score and 1-based rank.

    Example:
        >>> Hit(chunk_id=1, node_id=33, score=4.2, rank=1).rank
        1
    """

    chunk_id: int
    node_id: int
    score: float
    rank: int

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.rank < 1:
            raise ValueError("rank is 1-based")
        return self


class SubForest(_Frozen):
    """The retrieval-induced sub-forest: hit nodes plus all their ancestors.

    `nodes` maps node id to node, `roots` lists top-level node ids in display order and
    `hit_marks` maps node id to the number of hits landing directly on that node. `scores` sums the hit
    scores landing directly on each node, and `child_counts` gives each node's total number of children in
    the full tree, so a renderer can say how many siblings it collapsed.

    Example:
        >>> root = Node(id=1, corpus_id="docs", kind="site", title="docs/")
        >>> SubForest(roots=[1], nodes={1: root}, hit_marks={}).roots
        [1]
    """

    roots: list[int]
    nodes: dict[int, Node]
    hit_marks: dict[int, int]
    scores: dict[int, float] = Field(default_factory=dict)
    child_counts: dict[int, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [*self.roots, *self.hit_marks, *self.scores, *self.child_counts]
        missing = [i for i in ids if i not in self.nodes]
        if missing:
            raise ValueError(f"unknown node ids: {missing}")
        return self

    def render(self, budget_tokens: int, estimator: Callable[[str], int] | None = None) -> str:
        """Render the compact outline an agent sees after `search`, within `budget_tokens`.

        See `subforest.render.render` for the collapsing rules.

        Example:
            >>> root = Node(id=1, corpus_id="docs", kind="site", title="docs/")
            >>> SubForest(roots=[1], nodes={1: root}, hit_marks={}).render(100)
            'docs/ (site)'
        """
        from subforest.render import render

        return render(self, budget_tokens, estimator)
