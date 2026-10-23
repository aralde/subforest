"""MCP server exposing the agent tools over stdio. Requires the `subforest[mcp]` extra."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from mcp.server import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from subforest.policy import Policy
from subforest.retrievers import FTS5Retriever
from subforest.store import TreeStore
from subforest.tools import Toolkit, ToolResult

INSTRUCTIONS = """\
Navigate a documentation corpus by its structure.
1. `search` returns an outline of the documents and sections around the hits,
   with ids like [n31] and hit markers.
2. `expand`, `outline` and `siblings` show more of the tree around a node.
3. `read` returns a node's text with its breadcrumb.
   Prefer reading the most promising sections over re-searching.
Some calls may be blocked by a tool-order policy; the message says what to do instead."""

_READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


def _to_mcp(result: ToolResult) -> CallToolResult:
    # Some clients show only structured content when present, so it carries the text too.
    return CallToolResult(
        content=[TextContent(type="text", text=result.text)],
        structured_content={"text": result.text, **result.data},
        is_error=result.error or result.blocked,
    )


class _TurnClock:
    """MCP has no notion of an agent turn; treat a pause of `idle_seconds` between calls as a new turn."""

    def __init__(self, toolkit: Toolkit, idle_seconds: float, now: Callable[[], float]) -> None:
        self.toolkit = toolkit
        self.idle_seconds = idle_seconds
        self.now = now
        self.last: float | None = None

    def tick(self) -> None:
        current = self.now()
        if self.last is not None and current - self.last > self.idle_seconds:
            self.toolkit.new_turn()
        self.last = current


def create_server(
    toolkit: Toolkit, *, turn_idle_seconds: float = 120.0, now: Callable[[], float] = time.monotonic
) -> MCPServer:
    """Build an MCP server whose tools call `toolkit` (policy included).

    Example:
        >>> import asyncio
        >>> store = TreeStore()
        >>> server = create_server(Toolkit(store, FTS5Retriever(store)))
        >>> sorted(t.name for t in asyncio.run(server.list_tools()))
        ['expand', 'outline', 'read', 'search', 'siblings']
    """
    server: MCPServer = MCPServer(name="subforest", instructions=INSTRUCTIONS)
    clock = _TurnClock(toolkit, turn_idle_seconds, now)

    def run(name: str, **args: object) -> CallToolResult:
        clock.tick()
        return _to_mcp(toolkit.call(name, **args))

    @server.tool(annotations=_READ_ONLY)
    async def search(query: str, more_results: bool = False) -> CallToolResult:
        """Search the corpus. Returns an indented outline of the matching documents and sections with node ids
        ([n31]) and hit markers (●). Use more_results=true to see docs with weaker hits."""
        return run("search", query=query, more_results=more_results)

    @server.tool(annotations=_READ_ONLY)
    async def expand(node_id: str, depth: int = 1) -> CallToolResult:
        """Show the children of a node (e.g. "n31") down to `depth` levels, with their ids.
        "(+N)" means the child has N more children not shown."""
        return run("expand", node_id=node_id, depth=depth)

    @server.tool(annotations=_READ_ONLY)
    async def read(node_id: str, max_tokens: int = 800) -> CallToolResult:
        """Read a document or section (e.g. "n33") with its breadcrumb path.
        If it is too long, you get its own text plus a list of subsections to read separately."""
        return run("read", node_id=node_id, max_tokens=max_tokens)

    @server.tool(annotations=_READ_ONLY)
    async def siblings(node_id: str) -> CallToolResult:
        """List the siblings of a node in document order; the node itself is marked with ▸."""
        return run("siblings", node_id=node_id)

    @server.tool(annotations=_READ_ONLY)
    async def outline(doc_id: str) -> CallToolResult:
        """Show the full section tree of a document, by node id ("n29") or corpus-relative path
        ("guides/authentication.md")."""
        return run("outline", doc_id=doc_id)

    return server


def serve(
    db: Path,
    *,
    policy: Policy | None = None,
    budget_tokens: int = 400,
    turn_idle_seconds: float = 120.0,
) -> None:  # pragma: no cover - exercised through the CLI subprocess test
    """Serve the tools for the corpus in `db` over stdio until the client disconnects.

    Example:
        ``subforest serve --db corpus.db --policy policy.yaml``
    """
    with TreeStore(db) as store:
        toolkit = Toolkit(store, FTS5Retriever(store), policy=policy, budget_tokens=budget_tokens)
        create_server(toolkit, turn_idle_seconds=turn_idle_seconds).run("stdio")
