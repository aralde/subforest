"""Search adapters behind one `Retriever` protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from subforest.models import Hit
from subforest.retrievers.fts5 import FTS5Retriever

__all__ = ["FTS5Retriever", "Retriever"]


@runtime_checkable
class Retriever(Protocol):
    """Anything that turns a query into ranked chunk hits.

    Example:
        >>> from subforest import TreeStore
        >>> isinstance(FTS5Retriever(TreeStore()), Retriever)
        True
    """

    def search(self, query: str, k: int = 10) -> list[Hit]:
        """Return up to `k` hits, best first, with 1-based ranks."""
        ...
