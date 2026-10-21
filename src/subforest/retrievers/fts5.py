"""SQLite FTS5 (BM25) retriever over the chunks of a `TreeStore`."""

from __future__ import annotations

import re

from subforest.models import Hit
from subforest.store import TreeStore

_TERM = re.compile(r"\w+")

_CREATE = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    title, text, content='', tokenize='porter unicode61'
)
"""


def fts_query(query: str) -> str:
    """Turn free text into a safe FTS5 query: every word quoted, OR-ed together.

    Example:
        >>> fts_query('token "rotation" AND 429?')
        '"token" OR "rotation" OR "and" OR "429"'
    """
    terms = dict.fromkeys(t.lower() for t in _TERM.findall(query))
    return " OR ".join(f'"{t}"' for t in terms)


class FTS5Retriever:
    """BM25 search over chunk text and the title of the node each chunk belongs to.

    The index lives in the same database as the tree and is (re)built when its row count
    does not match the chunks table.

    Example:
        >>> from subforest import Chunk, Node
        >>> store = TreeStore()
        >>> store.add_nodes([Node(id=1, corpus_id="c", kind="doc", title="Auth")])
        >>> store.add_chunks([Chunk(id=7, node_id=1, text="Tokens expire.", start=0, end=14)])
        >>> [(h.chunk_id, h.node_id, h.rank) for h in FTS5Retriever(store).search("token")]
        [(7, 1, 1)]
    """

    def __init__(self, store: TreeStore) -> None:
        self._conn = store.connection
        self.ensure_index()

    def ensure_index(self) -> None:
        """Create the FTS5 index if missing and rebuild it if it is out of sync with the chunks.

        Example:
            >>> FTS5Retriever(TreeStore()).ensure_index()
        """
        with self._conn:
            self._conn.execute(_CREATE)
            indexed = self._conn.execute("SELECT count(*) FROM chunks_fts_docsize").fetchone()[0]
            total = self._conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
            if indexed == total:
                return
            self._conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('delete-all')")
            self._conn.execute(
                "INSERT INTO chunks_fts(rowid, title, text) "
                "SELECT c.id, n.title, c.text FROM chunks c JOIN nodes n ON n.id = c.node_id"
            )

    def search(self, query: str, k: int = 10) -> list[Hit]:
        """Return up to `k` chunk hits ranked by BM25 (higher score is better; ties broken by chunk id).

        Example:
            >>> FTS5Retriever(TreeStore()).search("?!")
            []
        """
        match = fts_query(query)
        if not match or k < 1:
            return []
        rows = self._conn.execute(
            "SELECT f.rowid, c.node_id, -bm25(chunks_fts) AS score "
            "FROM chunks_fts f JOIN chunks c ON c.id = f.rowid "
            "WHERE chunks_fts MATCH ? ORDER BY score DESC, f.rowid LIMIT ?",
            (match, k),
        ).fetchall()
        return [
            Hit(chunk_id=chunk_id, node_id=node_id, score=round(score, 6), rank=i)
            for i, (chunk_id, node_id, score) in enumerate(rows, start=1)
        ]
