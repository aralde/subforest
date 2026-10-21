"""Turn search hits into the retrieval-induced sub-forest."""

from __future__ import annotations

from collections.abc import Iterable

from subforest.models import Hit, Node, SubForest
from subforest.store import TreeStore


def induce(store: TreeStore, hits: Iterable[Hit]) -> SubForest:
    """Map hits to their nodes, add every ancestor, and union the paths across documents.

    `hit_marks` and `scores` aggregate the hits landing directly on each node; roots are ordered like
    `TreeStore.roots`. Raises `KeyError` if a hit points at an unknown node.

    Example:
        >>> store = TreeStore()
        >>> store.add_nodes([
        ...     Node(id=1, corpus_id="c", kind="site", title="docs/"),
        ...     Node(id=2, corpus_id="c", parent_id=1, kind="doc", title="Auth"),
        ...     Node(id=3, corpus_id="c", parent_id=2, kind="section", title="Tokens"),
        ... ])
        >>> forest = induce(store, [Hit(chunk_id=1, node_id=3, score=2.0, rank=1)])
        >>> sorted(forest.nodes), forest.roots, forest.hit_marks
        ([1, 2, 3], [1], {3: 1})
    """
    nodes: dict[int, Node] = {}
    marks: dict[int, int] = {}
    scores: dict[int, float] = {}
    for hit in hits:
        marks[hit.node_id] = marks.get(hit.node_id, 0) + 1
        scores[hit.node_id] = scores.get(hit.node_id, 0.0) + hit.score
        if hit.node_id in nodes:
            continue
        for node in [*store.ancestors(hit.node_id), store.get_node(hit.node_id)]:
            nodes.setdefault(node.id, node)
    roots = sorted((n for n in nodes.values() if n.parent_id is None), key=lambda n: (n.order, n.id))
    return SubForest(
        roots=[n.id for n in roots],
        nodes=nodes,
        hit_marks=marks,
        scores=scores,
        child_counts=store.child_counts(nodes),
    )
