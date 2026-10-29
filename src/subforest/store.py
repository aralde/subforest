"""SQLite-backed storage for the document tree and its chunks."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Self

from subforest.models import Chunk, Node

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY,
    corpus_id TEXT NOT NULL,
    parent_id INTEGER REFERENCES nodes(id),
    kind TEXT NOT NULL CHECK (kind IN ('site', 'dir', 'doc', 'section')),
    title TEXT NOT NULL,
    url TEXT,
    path TEXT,
    ord INTEGER NOT NULL DEFAULT 0,
    span_start INTEGER,
    span_end INTEGER
);
CREATE INDEX IF NOT EXISTS nodes_parent ON nodes(parent_id, ord);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    node_id INTEGER NOT NULL REFERENCES nodes(id),
    text TEXT NOT NULL,
    start INTEGER NOT NULL,
    "end" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_node ON chunks(node_id, start);
CREATE TABLE IF NOT EXISTS doc_texts (
    node_id INTEGER PRIMARY KEY REFERENCES nodes(id),
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS nodes_path ON nodes(corpus_id, path);
"""

_NODE_COLS = "id, corpus_id, parent_id, kind, title, url, path, ord, span_start, span_end"

_ANCESTORS = f"""
WITH RECURSIVE up(id, depth) AS (
    SELECT parent_id, 1 FROM nodes WHERE id = ? AND parent_id IS NOT NULL
    UNION ALL
    SELECT n.parent_id, up.depth + 1 FROM nodes n JOIN up ON n.id = up.id
    WHERE n.parent_id IS NOT NULL
)
SELECT {_NODE_COLS} FROM nodes JOIN up USING (id) ORDER BY up.depth DESC
"""


def _row_to_node(row: sqlite3.Row) -> Node:
    span = None if row["span_start"] is None else (row["span_start"], row["span_end"])
    return Node(
        id=row["id"],
        corpus_id=row["corpus_id"],
        parent_id=row["parent_id"],
        kind=row["kind"],
        title=row["title"],
        url=row["url"],
        path=row["path"],
        order=row["ord"],
        span=span,
    )


class TreeStore:
    """Nodes and chunks of one or more corpora, stored in SQLite with parent pointers.

    Example:
        >>> with TreeStore() as store:
        ...     store.add_nodes([
        ...         Node(id=1, corpus_id="c", kind="site", title="docs/"),
        ...         Node(id=2, corpus_id="c", parent_id=1, kind="doc", title="Auth"),
        ...     ])
        ...     [n.id for n in store.ancestors(2)]
        [1]
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying SQLite connection, for adapters that add their own tables (e.g. FTS5).

        Example:
            >>> TreeStore().connection.execute("SELECT count(*) FROM nodes").fetchone()[0]
            0
        """
        return self._conn

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying connection.

        Example:
            >>> TreeStore().close()
        """
        self._conn.close()

    def add_nodes(self, nodes: Iterable[Node]) -> None:
        """Insert nodes in one transaction; parents must be inserted before (or with) their children.

        Example:
            >>> store = TreeStore()
            >>> store.add_nodes([Node(id=1, corpus_id="c", kind="site", title="docs/")])
            >>> store.get_node(1).title
            'docs/'
        """
        rows = [
            (
                n.id,
                n.corpus_id,
                n.parent_id,
                n.kind,
                n.title,
                n.url,
                n.path,
                n.order,
                n.span[0] if n.span else None,
                n.span[1] if n.span else None,
            )
            for n in nodes
        ]
        with self._conn:
            self._conn.executemany(
                f"INSERT INTO nodes ({_NODE_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
            )

    def add_chunks(self, chunks: Iterable[Chunk]) -> None:
        """Insert chunks in one transaction; each chunk's node must already exist.

        Example:
            >>> store = TreeStore()
            >>> store.add_nodes([Node(id=1, corpus_id="c", kind="doc", title="Auth")])
            >>> store.add_chunks([Chunk(id=1, node_id=1, text="Use tokens.", start=0, end=11)])
            >>> [c.text for c in store.chunks(1)]
            ['Use tokens.']
        """
        rows = [(c.id, c.node_id, c.text, c.start, c.end) for c in chunks]
        with self._conn:
            self._conn.executemany(
                'INSERT INTO chunks (id, node_id, text, start, "end") VALUES (?, ?, ?, ?, ?)', rows
            )

    def add_doc_texts(self, texts: Mapping[int, str]) -> None:
        """Store the full source text of document nodes, so tools can read sections with their headings.

        Example:
            >>> store = TreeStore()
            >>> store.add_nodes([Node(id=1, corpus_id="c", kind="doc", title="Auth")])
            >>> store.add_doc_texts({1: "# Auth"})
            >>> store.doc_text(1)
            '# Auth'
        """
        with self._conn:
            self._conn.executemany("INSERT INTO doc_texts (node_id, text) VALUES (?, ?)", texts.items())

    def doc_text(self, node_id: int) -> str | None:
        """Return the stored source text of a document node, or `None` if it has none.

        Example:
            >>> TreeStore().doc_text(1) is None
            True
        """
        row = self._conn.execute("SELECT text FROM doc_texts WHERE node_id = ?", (node_id,)).fetchone()
        return None if row is None else str(row["text"])

    def find_by_path(self, path: str, corpus_id: str | None = None) -> Node | None:
        """Return the node stored with this exact relative `path` (first by id if several corpora share it).

        This is a database lookup only; it never touches the filesystem.

        Example:
            >>> store = TreeStore()
            >>> store.add_nodes([Node(id=1, corpus_id="c", kind="doc", title="Auth", path="guides/auth.md")])
            >>> store.find_by_path("guides/auth.md").id
            1
        """
        sql = f"SELECT {_NODE_COLS} FROM nodes WHERE path = ?"
        params: tuple[str, ...] = (path,)
        if corpus_id is not None:
            sql += " AND corpus_id = ?"
            params = (path, corpus_id)
        row = self._conn.execute(sql + " ORDER BY id LIMIT 1", params).fetchone()
        return None if row is None else _row_to_node(row)

    def get_node(self, node_id: int) -> Node:
        """Return a node by id; raise `KeyError` if it does not exist.

        Example:
            >>> TreeStore().get_node(99)
            Traceback (most recent call last):
            ...
            KeyError: 'unknown node 99'
        """
        row = self._conn.execute(f"SELECT {_NODE_COLS} FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown node {node_id}")
        return _row_to_node(row)

    def children(self, node_id: int) -> list[Node]:
        """Return the direct children of a node, in document order.

        Example:
            >>> store = TreeStore()
            >>> store.add_nodes([
            ...     Node(id=1, corpus_id="c", kind="doc", title="Auth"),
            ...     Node(id=3, corpus_id="c", parent_id=1, kind="section", title="B", order=1),
            ...     Node(id=2, corpus_id="c", parent_id=1, kind="section", title="A", order=0),
            ... ])
            >>> [n.title for n in store.children(1)]
            ['A', 'B']
        """
        rows = self._conn.execute(
            f"SELECT {_NODE_COLS} FROM nodes WHERE parent_id = ? ORDER BY ord, id", (node_id,)
        ).fetchall()
        return [_row_to_node(r) for r in rows]

    def roots(self, corpus_id: str | None = None) -> list[Node]:
        """Return the top-level nodes, optionally restricted to one corpus.

        Example:
            >>> store = TreeStore()
            >>> store.add_nodes([Node(id=1, corpus_id="c", kind="site", title="docs/")])
            >>> [n.id for n in store.roots("c")]
            [1]
        """
        sql = f"SELECT {_NODE_COLS} FROM nodes WHERE parent_id IS NULL"
        params: tuple[str, ...] = ()
        if corpus_id is not None:
            sql += " AND corpus_id = ?"
            params = (corpus_id,)
        rows = self._conn.execute(sql + " ORDER BY ord, id", params).fetchall()
        return [_row_to_node(r) for r in rows]

    def ancestors(self, node_id: int) -> list[Node]:
        """Return the ancestors of a node from the root down to its parent (the node itself excluded).

        Raises `KeyError` if the node does not exist.

        Example:
            >>> store = TreeStore()
            >>> store.add_nodes([
            ...     Node(id=1, corpus_id="c", kind="site", title="docs/"),
            ...     Node(id=2, corpus_id="c", parent_id=1, kind="doc", title="Auth"),
            ...     Node(id=3, corpus_id="c", parent_id=2, kind="section", title="Tokens"),
            ... ])
            >>> [n.title for n in store.ancestors(3)]
            ['docs/', 'Auth']
        """
        self.get_node(node_id)
        rows = self._conn.execute(_ANCESTORS, (node_id,)).fetchall()
        return [_row_to_node(r) for r in rows]

    def child_counts(self, node_ids: Iterable[int]) -> dict[int, int]:
        """Return how many direct children each of the given nodes has (0 for leaves).

        Example:
            >>> store = TreeStore()
            >>> store.add_nodes([
            ...     Node(id=1, corpus_id="c", kind="doc", title="Auth"),
            ...     Node(id=2, corpus_id="c", parent_id=1, kind="section", title="A"),
            ... ])
            >>> store.child_counts([1, 2])
            {1: 1, 2: 0}
        """
        ids = list(dict.fromkeys(node_ids))
        counts = dict.fromkeys(ids, 0)
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            marks = ", ".join("?" * len(batch))
            rows = self._conn.execute(
                f"SELECT parent_id, count(*) FROM nodes WHERE parent_id IN ({marks}) GROUP BY parent_id",
                batch,
            )
            counts.update({parent: n for parent, n in rows})
        return counts

    def chunk(self, chunk_id: int) -> Chunk:
        """Return one chunk by id; raises `KeyError` if it does not exist.

        Example:
            >>> TreeStore().chunk(1)
            Traceback (most recent call last):
            ...
            KeyError: 'no chunk 1'
        """
        row = self._conn.execute(
            'SELECT id, node_id, text, start, "end" FROM chunks WHERE id = ?', (chunk_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no chunk {chunk_id}")
        return Chunk(
            id=row["id"], node_id=row["node_id"], text=row["text"], start=row["start"], end=row["end"]
        )

    def chunks(self, node_id: int) -> list[Chunk]:
        """Return the chunks owned by a node, in text order.

        Example:
            >>> TreeStore().chunks(1)
            []
        """
        rows = self._conn.execute(
            'SELECT id, node_id, text, start, "end" FROM chunks WHERE node_id = ? ORDER BY start, id',
            (node_id,),
        ).fetchall()
        return [
            Chunk(id=r["id"], node_id=r["node_id"], text=r["text"], start=r["start"], end=r["end"])
            for r in rows
        ]
