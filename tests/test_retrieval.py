import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from subforest import Chunk, Hit, Node, SubForest, TreeStore, estimate_tokens, induce, render
from subforest.build import build_corpus
from subforest.retrievers import FTS5Retriever, Retriever
from subforest.retrievers.fts5 import fts_query

SNAPSHOTS = Path(__file__).parent / "snapshots"
QUERIES = ["token expire rotate", "rate limit 429", "webhook signature", "export notes markdown", "refund"]


@pytest.fixture
def built(corpus_dir: Path) -> Iterator[TreeStore]:
    with TreeStore() as store:
        build_corpus(corpus_dir, corpus_id="docs").write(store)
        yield store


def test_fts5_is_a_retriever(built: TreeStore) -> None:
    assert isinstance(FTS5Retriever(built), Retriever)


def test_fts5_ranks_and_scores(built: TreeStore) -> None:
    hits = FTS5Retriever(built).search("token", k=3)
    assert [h.rank for h in hits] == [1, 2, 3]
    assert hits[0].score >= hits[1].score >= hits[2].score
    top = FTS5Retriever(built).search("webhook signature", k=3)
    assert built.get_node(top[0].node_id).title == "Verifying signatures"


def test_fts5_matches_node_titles_and_stems(built: TreeStore) -> None:
    hits = FTS5Retriever(built).search("rotating", k=1)
    assert built.get_node(hits[0].node_id).title == "Rotating tokens"


def test_fts5_survives_query_syntax() -> None:
    assert fts_query('NEAR(a b) "x" -y *') == '"near" OR "a" OR "b" OR "x" OR "y"'
    with TreeStore() as store:
        assert FTS5Retriever(store).search('"unbalanced AND (', k=5) == []


def test_fts5_reindexes_new_chunks(built: TreeStore) -> None:
    retriever = FTS5Retriever(built)
    assert retriever.search("zebra") == []
    built.add_nodes([Node(id=1000, corpus_id="docs", kind="doc", title="Zoo")])
    built.add_chunks([Chunk(id=1000, node_id=1000, text="A zebra.", start=0, end=8)])
    retriever.ensure_index()
    assert [h.chunk_id for h in retriever.search("zebra")] == [1000]


@pytest.mark.parametrize("query", QUERIES)
def test_induced_forest_contains_every_hit_ancestor(built: TreeStore, query: str) -> None:
    hits = FTS5Retriever(built).search(query, k=10)
    assert hits
    forest = induce(built, hits)
    for hit in hits:
        assert hit.node_id in forest.nodes
        for ancestor in built.ancestors(hit.node_id):
            assert forest.nodes[ancestor.id] == ancestor
    assert sum(forest.hit_marks.values()) == len(hits)
    assert forest.roots == [n.id for n in forest.nodes.values() if n.parent_id is None]


def test_induce_unknown_node(built: TreeStore) -> None:
    with pytest.raises(KeyError):
        induce(built, [Hit(chunk_id=1, node_id=9999, score=1.0, rank=1)])


def test_induce_no_hits(built: TreeStore) -> None:
    assert induce(built, []) == SubForest(roots=[], nodes={}, hit_marks={})
    assert render(induce(built, []), 100) == ""


@pytest.mark.parametrize("budget", [400, 120, 60])
def test_render_golden(built: TreeStore, budget: int) -> None:
    forest = induce(built, FTS5Retriever(built).search("token expire rotate", k=10))
    got = forest.render(budget) + "\n"
    golden = SNAPSHOTS / f"render_{budget}.txt"
    if os.environ.get("SUBFOREST_UPDATE_SNAPSHOTS"):
        golden.write_text(got)
    assert got == golden.read_text()
    assert estimate_tokens(got.rstrip("\n")) <= budget


@pytest.mark.parametrize("query", QUERIES)
def test_render_respects_budget_above_minimum(built: TreeStore, query: str) -> None:
    forest = induce(built, FTS5Retriever(built).search(query, k=10))
    minimum = estimate_tokens(forest.render(0))
    previous = None
    for budget in range(minimum, 600, 7):
        text = forest.render(budget)
        assert estimate_tokens(text) <= budget
        assert previous is None or len(text) >= len(previous)
        previous = text


def test_render_never_hides_strongest_doc(built: TreeStore) -> None:
    forest = induce(built, FTS5Retriever(built).search("token expire rotate", k=10))
    assert "Authentication [n" in forest.render(0)


def test_render_uses_custom_estimator(built: TreeStore) -> None:
    forest = induce(built, FTS5Retriever(built).search("token", k=10))
    lines = forest.render(8, estimator=lambda s: s.count("\n") + 1).splitlines()
    assert len(lines) <= 8


def test_render_pluralizes_and_marks() -> None:
    nodes = {
        1: Node(id=1, corpus_id="c", kind="doc", title="Doc"),
        2: Node(id=2, corpus_id="c", parent_id=1, kind="section", title="A"),
    }
    forest = SubForest(roots=[1], nodes=nodes, hit_marks={2: 7}, child_counts={1: 2, 2: 0})
    assert render(forest, 100).splitlines() == [
        "Doc [n1] ●●●●● 7 hits",
        "  A [n2] ●●●●● 7 hits",
        "  … +1 section",
    ]
