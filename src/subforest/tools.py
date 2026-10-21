"""Read-only agent tools over a built corpus: search, expand, read, siblings and outline.

Tools only read the `TreeStore` database; they never open files, so path arguments cannot reach the
filesystem. Every tool returns a `ToolResult` with the text the agent sees and a JSON-ready payload.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from subforest.induce import induce
from subforest.models import Node
from subforest.policy import Policy, TurnState
from subforest.retrievers import Retriever
from subforest.store import TreeStore
from subforest.tokens import estimate_tokens

_NODE_ID = re.compile(r"^n?(\d+)$")
TOOL_NAMES = ("search", "expand", "read", "siblings", "outline")


class ToolResult(BaseModel):
    """What a tool returns: `text` for the agent, `data` for programs, and whether it failed or was blocked.

    Example:
        >>> ToolResult(text="ok").model_dump()
        {'text': 'ok', 'data': {}, 'error': False, 'blocked': False}
    """

    model_config = ConfigDict(frozen=True)

    text: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: bool = False
    blocked: bool = False


class ToolError(Exception):
    """A bad tool argument; its message is shown to the agent."""


def parse_node_id(value: str | int) -> int:
    """Accept `n31`, `"31"` or `31` and return the integer id.

    Example:
        >>> parse_node_id("n31"), parse_node_id(" 7 "), parse_node_id(5)
        (31, 7, 5)
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    m = _NODE_ID.match(str(value).strip())
    if not m:
        raise ToolError(f"Invalid node id {value!r}. Use ids shown in results, like n31.")
    return int(m.group(1))


def _summary(node: Node) -> dict[str, Any]:
    return {"id": node.short_id, "kind": node.kind, "title": node.title, "path": node.path, "url": node.url}


class Toolkit:
    """The agent-facing tools, sharing one store, retriever, render budget and per-turn policy state.

    `extra_tools` adds harness-provided tools (e.g. `semantic_search`) so the policy covers them too.

    Example:
        >>> from subforest.build import DocSource, assemble
        >>> from subforest.retrievers import FTS5Retriever
        >>> store = TreeStore()
        >>> assemble([DocSource(parts=("auth.md",), text="# Auth\\n## Tokens\\nTokens expire.\\n")],
        ...          corpus_id="docs").write(store)
        >>> tools = Toolkit(store, FTS5Retriever(store))
        >>> print(tools.call("search", query="expire").text)
        docs/ (site)
          Auth [n2] ● 1 hit
            Tokens [n3] ● 1 hit
    """

    def __init__(
        self,
        store: TreeStore,
        retriever: Retriever,
        *,
        policy: Policy | None = None,
        budget_tokens: int = 400,
        k: int = 10,
        more_k: int = 30,
        estimator: Callable[[str], int] | None = None,
        extra_tools: Mapping[str, Callable[..., ToolResult]] | None = None,
    ) -> None:
        self.store = store
        self.retriever = retriever
        self.state = TurnState(policy)
        self.budget_tokens = budget_tokens
        self.k = k
        self.more_k = more_k
        self.estimate = estimator or estimate_tokens
        self._tools: dict[str, Callable[..., ToolResult]] = {
            "search": self.search,
            "expand": self.expand,
            "read": self.read,
            "siblings": self.siblings,
            "outline": self.outline,
            **(extra_tools or {}),
        }
        self._hits: dict[int, int] = {}

    @property
    def names(self) -> list[str]:
        """Names of every callable tool, built-in first.

        Example:
            >>> from subforest.retrievers import FTS5Retriever
            >>> Toolkit(TreeStore(), FTS5Retriever(TreeStore())).names
            ['search', 'expand', 'read', 'siblings', 'outline']
        """
        return list(self._tools)

    def new_turn(self) -> None:
        """Reset the per-turn policy state (call at the start of each agent turn)."""
        self.state.new_turn()

    def call(self, name: str, **args: Any) -> ToolResult:
        """Run a tool by name after checking the policy; bad arguments become error results, not exceptions.

        Example:
            >>> from subforest.retrievers import FTS5Retriever
            >>> Toolkit(TreeStore(), FTS5Retriever(TreeStore())).call("read", node_id="x").error
            True
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(text=f"Unknown tool {name!r}. Available: {', '.join(self._tools)}.", error=True)
        if message := self.state.attempt(name):
            return ToolResult(text=message, data={"blocked_by_policy": True}, blocked=True)
        try:
            return tool(**args)
        except ToolError as exc:
            return ToolResult(text=str(exc), data={"error": str(exc)}, error=True)
        except TypeError as exc:
            return ToolResult(text=f"Bad arguments for {name}: {exc}", data={"error": str(exc)}, error=True)

    def _node(self, ref: str | int) -> Node:
        if isinstance(ref, str) and ("/" in ref or ref.endswith((".md", ".mdx"))):
            return self._node_by_path(ref)
        try:
            return self.store.get_node(parse_node_id(ref))
        except KeyError:
            raise ToolError(f"Unknown node {ref!r}. Use ids shown in results, like n31.") from None

    def _node_by_path(self, path: str) -> Node:
        parts = path.replace("\\", "/").split("/")
        if path.startswith(("/", "~")) or ".." in parts or ":" in parts[0]:
            raise ToolError(f"Rejected path {path!r}: use a corpus-relative path without '..'.")
        node = self.store.find_by_path("/".join(p for p in parts if p not in ("", ".")))
        if node is None:
            raise ToolError(f"No document at {path!r}. Use ids or paths shown in results.")
        return node

    def _breadcrumb(self, node: Node) -> str:
        return (
            " › ".join([*(a.title for a in self.store.ancestors(node.id)), node.title])
            + f" [{node.short_id}]"
        )

    def _marks(self, node_id: int) -> str:
        hits = self._hits.get(node_id, 0)
        return f" ● {hits} hit{'' if hits == 1 else 's'}" if hits else ""

    def _tree_lines(self, node: Node, depth: int, max_depth: int, out: list[str]) -> None:
        children = self.store.children(node.id)
        for child in children:
            more = self.store.child_counts([child.id])[child.id]
            hidden = f" (+{more})" if more and depth + 1 >= max_depth else ""
            out.append(f"{'  ' * (depth + 1)}{child.title} [{child.short_id}]{self._marks(child.id)}{hidden}")
            if depth + 1 < max_depth:
                self._tree_lines(child, depth + 1, max_depth, out)

    def _fit_tree(self, node: Node, max_depth: int) -> tuple[str, int]:
        header = self._breadcrumb(node)
        depth = max_depth
        while True:
            lines = [header]
            self._tree_lines(node, 0, depth, lines)
            text = "\n".join(lines)
            if depth <= 1 or self.estimate(text) <= self.budget_tokens:
                return text, depth
            depth -= 1

    def search(self, query: str, more_results: bool = False) -> ToolResult:
        """Search the corpus and return the induced sub-forest around the hits.

        `more_results=True` widens the search (more hits, double budget) to show weaker docs.

        Example:
            >>> from subforest.retrievers import FTS5Retriever
            >>> Toolkit(TreeStore(), FTS5Retriever(TreeStore())).search("anything").text
            'No results. Try other words, or outline a document you already know.'
        """
        if not query.strip():
            raise ToolError("search needs a non-empty query.")
        k, budget = (self.more_k, self.budget_tokens * 2) if more_results else (self.k, self.budget_tokens)
        hits = self.retriever.search(query, k=k)
        if not hits:
            return ToolResult(
                text="No results. Try other words, or outline a document you already know.",
                data={"query": query, "hits": []},
            )
        forest = induce(self.store, hits)
        self._hits = {}
        for node_id, count in forest.hit_marks.items():
            current: int | None = node_id
            while current is not None:
                self._hits[current] = self._hits.get(current, 0) + count
                current = forest.nodes[current].parent_id
        return ToolResult(
            text=forest.render(budget, self.estimate),
            data={
                "query": query,
                "hits": [{**h.model_dump(), "node": f"n{h.node_id}"} for h in hits],
                "nodes": [f"n{i}" for i in sorted(forest.nodes)],
            },
        )

    def expand(self, node_id: str | int, depth: int = 1) -> ToolResult:
        """Show a node's children (down to `depth` levels, reduced if over budget) with their ids.

        `(+N)` marks a child with N children of its own that are not shown.

        Example:
            >>> from subforest.retrievers import FTS5Retriever
            >>> Toolkit(TreeStore(), FTS5Retriever(TreeStore())).call("expand", node_id="n1", depth=0).error
            True
        """
        if depth < 1:
            raise ToolError("depth must be at least 1.")
        node = self._node(node_id)
        text, shown = self._fit_tree(node, depth)
        children = [_summary(c) for c in self.store.children(node.id)]
        return ToolResult(text=text, data={"node": _summary(node), "depth": shown, "children": children})

    def outline(self, doc_id: str | int) -> ToolResult:
        """Show the full section tree of a document (or any node), collapsing depth to fit the budget.

        Accepts a node id or a corpus-relative document path such as `guides/authentication.md`.

        Example:
            >>> from subforest.retrievers import FTS5Retriever
            >>> Toolkit(TreeStore(), FTS5Retriever(TreeStore())).call("outline", doc_id="../etc/passwd").text
            "Rejected path '../etc/passwd': use a corpus-relative path without '..'."
        """
        node = self._node(doc_id)
        text, shown = self._fit_tree(node, 64)
        return ToolResult(text=text, data={"node": _summary(node), "depth": shown})

    def siblings(self, node_id: str | int) -> ToolResult:
        """List a node's siblings in document order, marking the node itself with `▸`.

        Example:
            >>> from subforest.retrievers import FTS5Retriever
            >>> Toolkit(TreeStore(), FTS5Retriever(TreeStore())).call("siblings", node_id=3).text
            'Unknown node 3. Use ids shown in results, like n31.'
        """
        node = self._node(node_id)
        if node.parent_id is None:
            peers = self.store.roots()
            header = "(top level)"
        else:
            parent = self.store.get_node(node.parent_id)
            peers = self.store.children(parent.id)
            header = self._breadcrumb(parent)
        lines = [header]
        for peer in peers:
            mark = "▸ " if peer.id == node.id else "  "
            lines.append(f"{mark}{peer.title} [{peer.short_id}]{self._marks(peer.id)}")
        return ToolResult(
            text="\n".join(lines), data={"node": _summary(node), "siblings": [_summary(p) for p in peers]}
        )

    def read(self, node_id: str | int, max_tokens: int = 800) -> ToolResult:
        """Return a node's text with its breadcrumb path, within `max_tokens`.

        If the whole node does not fit, returns its own text and lists its subsections to read next;
        if even that does not fit, cuts at a paragraph boundary and says so.

        Example:
            >>> from subforest.retrievers import FTS5Retriever
            >>> tools = Toolkit(TreeStore(), FTS5Retriever(TreeStore()))
            >>> tools.call("read", node_id="n1", max_tokens=0).error
            True
        """
        if max_tokens < 1:
            raise ToolError("max_tokens must be at least 1.")
        node = self._node(node_id)
        header = self._breadcrumb(node)
        doc = (
            node
            if node.kind == "doc"
            else next((a for a in reversed(self.store.ancestors(node.id)) if a.kind == "doc"), None)
        )
        source = self.store.doc_text(doc.id) if doc else None
        if node.kind in ("site", "dir") or source is None or node.span is None:
            where = node.url or node.path or "this node"
            raise ToolError(
                f"{header} has no readable text ({where}). "
                "Use expand or outline to find documents and sections."
            )

        start, end = node.span
        body = source[start:end].strip()
        data: dict[str, Any] = {"node": _summary(node), "breadcrumb": header, "span": [start, end]}
        text = f"{header}\n\n{body}"
        if self.estimate(text) <= max_tokens:
            return ToolResult(text=text, data={**data, "complete": True})

        children = self.store.children(node.id)
        own_end = children[0].span[0] if children and children[0].span else end
        own = source[start:own_end].strip()
        listing = [f"- {c.title} [{c.short_id}]" for c in children]
        tail = "\n\nSubsections (read them separately):\n" + "\n".join(listing) if listing else ""
        text = f"{header}\n\n{own}{tail}"
        if self.estimate(text) > max_tokens:
            note = "\n\n… [cut to fit max_tokens; raise max_tokens or read a subsection]"
            kept: list[str] = []
            for paragraph in own.split("\n\n"):
                candidate = "\n\n".join([*kept, paragraph])
                if self.estimate(f"{header}\n\n{candidate}{note}{tail}") > max_tokens:
                    break
                kept.append(paragraph)
            text = f"{header}\n\n" + "\n\n".join(kept) + note + tail
        return ToolResult(
            text=text,
            data={**data, "complete": False, "subsections": [_summary(c) for c in children]},
        )
