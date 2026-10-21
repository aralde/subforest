import sqlite3

import pytest

from subforest import Chunk, Node, TreeStore


def titles(nodes: list[Node]) -> list[str]:
    return [n.title for n in nodes]


def test_ancestors_root_first(store: TreeStore) -> None:
    assert titles(store.ancestors(34)) == ["docs/", "guides/", "Authentication", "Tokens"]


def test_ancestors_of_root_is_empty(store: TreeStore) -> None:
    assert store.ancestors(1) == []


def test_ancestors_of_direct_child(store: TreeStore) -> None:
    assert titles(store.ancestors(50)) == ["docs/"]


def test_ancestors_unknown_node(store: TreeStore) -> None:
    with pytest.raises(KeyError):
        store.ancestors(999)


def test_ancestors_round_trip_fields(store: TreeStore) -> None:
    doc = store.ancestors(33)[-1]
    assert doc == Node(
        id=31,
        corpus_id="larch",
        parent_id=12,
        kind="doc",
        title="Authentication",
        path="guides/authentication.md",
        span=(0, 900),
    )


def test_ancestors_deep_chain() -> None:
    with TreeStore() as s:
        s.add_nodes([Node(id=0, corpus_id="c", kind="site", title="root")])
        s.add_nodes(
            Node(id=i, corpus_id="c", parent_id=i - 1, kind="section", title=f"s{i}") for i in range(1, 500)
        )
        assert [n.id for n in s.ancestors(499)] == list(range(499))


def test_children_ordered(store: TreeStore) -> None:
    assert titles(store.children(31)) == ["Tokens", "OAuth"]
    assert store.children(58) == []


def test_roots_by_corpus(store: TreeStore) -> None:
    assert [n.id for n in store.roots()] == [1, 100]
    assert [n.id for n in store.roots("other")] == [100]


def test_chunks_ordered(store: TreeStore) -> None:
    store.add_chunks(
        [
            Chunk(id=2, node_id=33, text="Tokens expire.", start=300, end=314),
            Chunk(id=1, node_id=33, text="Send a bearer token.", start=130, end=150),
        ]
    )
    assert [c.id for c in store.chunks(33)] == [1, 2]


def test_orphan_rejected() -> None:
    with TreeStore() as s, pytest.raises(sqlite3.IntegrityError):
        s.add_nodes([Node(id=2, corpus_id="c", parent_id=1, kind="doc", title="x")])


def test_chunk_needs_node(store: TreeStore) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.add_chunks([Chunk(id=1, node_id=999, text="x", start=0, end=1)])


def test_persists_to_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "corpus.db"
    with TreeStore(db) as s:
        s.add_nodes([Node(id=1, corpus_id="c", kind="site", title="docs/")])
    with TreeStore(db) as s:
        assert s.get_node(1).title == "docs/"
