from collections.abc import Iterator
from pathlib import Path

import pytest

from subforest import Node, TreeStore

CORPUS = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def corpus_dir() -> Path:
    return CORPUS


@pytest.fixture
def store() -> Iterator[TreeStore]:
    with TreeStore() as s:
        s.add_nodes(
            [
                Node(id=1, corpus_id="larch", kind="site", title="docs/"),
                Node(id=12, corpus_id="larch", parent_id=1, kind="dir", title="guides/", order=0),
                Node(id=50, corpus_id="larch", parent_id=1, kind="dir", title="api/", order=1),
                Node(
                    id=31,
                    corpus_id="larch",
                    parent_id=12,
                    kind="doc",
                    title="Authentication",
                    path="guides/authentication.md",
                    span=(0, 900),
                ),
                Node(
                    id=33,
                    corpus_id="larch",
                    parent_id=31,
                    kind="section",
                    title="Tokens",
                    span=(120, 400),
                    order=0,
                ),
                Node(
                    id=34,
                    corpus_id="larch",
                    parent_id=33,
                    kind="section",
                    title="Rotating tokens",
                    span=(260, 400),
                    order=0,
                ),
                Node(
                    id=35,
                    corpus_id="larch",
                    parent_id=31,
                    kind="section",
                    title="OAuth",
                    span=(400, 600),
                    order=1,
                ),
                Node(
                    id=58,
                    corpus_id="larch",
                    parent_id=50,
                    kind="doc",
                    title="Sessions",
                    path="api/sessions.md",
                ),
                Node(id=100, corpus_id="other", kind="site", title="other/"),
            ]
        )
        yield s
