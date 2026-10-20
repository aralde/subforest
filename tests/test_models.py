import pytest
from pydantic import ValidationError

from subforest import Chunk, Hit, Node, SubForest


def test_node_rejects_self_parent() -> None:
    with pytest.raises(ValidationError):
        Node(id=1, corpus_id="c", parent_id=1, kind="doc", title="x")


def test_node_rejects_bad_span() -> None:
    with pytest.raises(ValidationError):
        Node(id=1, corpus_id="c", kind="section", title="x", span=(10, 5))


def test_node_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        Node(id=1, corpus_id="c", kind="page", title="x")  # type: ignore[arg-type]


def test_node_is_frozen() -> None:
    node = Node(id=1, corpus_id="c", kind="doc", title="x")
    with pytest.raises(ValidationError):
        node.title = "y"  # type: ignore[misc]


def test_chunk_rejects_bad_range() -> None:
    with pytest.raises(ValidationError):
        Chunk(id=1, node_id=1, text="x", start=5, end=4)


def test_hit_rank_is_one_based() -> None:
    with pytest.raises(ValidationError):
        Hit(chunk_id=1, node_id=1, score=1.0, rank=0)


def test_subforest_rejects_unknown_ids() -> None:
    root = Node(id=1, corpus_id="c", kind="site", title="docs/")
    with pytest.raises(ValidationError):
        SubForest(roots=[1], nodes={1: root}, hit_marks={2: 1})


def test_short_id() -> None:
    assert Node(id=58, corpus_id="c", kind="doc", title="Sessions").short_id == "n58"
