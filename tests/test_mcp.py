import json
import sys
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest
from mcp import Client, StdioServerParameters

from subforest import TreeStore
from subforest.build import build_corpus
from subforest.cli import main
from subforest.mcp import create_server
from subforest.policy import Policy
from subforest.retrievers import FTS5Retriever
from subforest.tools import Toolkit

POLICY = Path(__file__).parents[1] / "examples" / "policies" / "read-before-semantic-search.yaml"


@pytest.fixture
def toolkit(corpus_dir: Path) -> Iterator[Toolkit]:
    with TreeStore() as store:
        build_corpus(corpus_dir, corpus_id="docs").write(store)
        yield Toolkit(store, FTS5Retriever(store), policy=Policy.load(POLICY), budget_tokens=250)


def text_of(result: object) -> str:
    return "".join(getattr(c, "text", "") for c in getattr(result, "content", []))


def test_tools_listed_and_callable_in_process(toolkit: Toolkit) -> None:
    async def scenario() -> None:
        async with Client(create_server(toolkit)) as client:
            listed = await client.list_tools()
            tools = {t.name: t for t in listed.tools}
            assert sorted(tools) == ["expand", "outline", "read", "search", "siblings"]
            assert tools["read"].annotations is not None and tools["read"].annotations.read_only_hint
            assert set(tools["search"].input_schema["properties"]) == {"query", "more_results"}

            found = await client.call_tool("search", {"query": "rotate token"})
            assert not found.is_error and "Rotating tokens [n" in text_of(found)
            assert found.structured_content is not None and found.structured_content["hits"]
            assert found.structured_content["text"] == text_of(found)

            again = await client.call_tool("search", {"query": "token"})
            assert again.is_error and again.structured_content == {
                "text": text_of(again),
                "blocked_by_policy": True,
            }

            read = await client.call_tool("read", {"node_id": "n30"})
            assert "Tokens expire after 90 days" in text_of(read)
            for name, args in [
                ("expand", {"node_id": "n29"}),
                ("siblings", {"node_id": "n30"}),
                ("outline", {"doc_id": "guides/authentication.md"}),
            ]:
                result = await client.call_tool(name, args)
                assert not result.is_error, (name, text_of(result))

            bad = await client.call_tool("read", {"node_id": "../../etc/passwd"})
            assert bad.is_error

    anyio.run(scenario)


def test_idle_gap_starts_new_turn(toolkit: Toolkit) -> None:
    clock = [0.0]

    async def scenario() -> None:
        server = create_server(toolkit, turn_idle_seconds=10, now=lambda: clock[0])
        async with Client(server) as client:
            assert not (await client.call_tool("search", {"query": "token"})).is_error
            clock[0] = 5
            assert (await client.call_tool("search", {"query": "token"})).is_error
            clock[0] = 20
            assert not (await client.call_tool("search", {"query": "token"})).is_error

    anyio.run(scenario)


def test_serve_over_stdio_subprocess(corpus_dir: Path, tmp_path: Path) -> None:
    db = tmp_path / "corpus.db"
    assert main(["build", str(corpus_dir), "--db", str(db), "--corpus-id", "docs"]) == 0
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "subforest.cli", "serve", "--db", str(db), "--policy", str(POLICY)],
    )

    async def scenario() -> None:
        async with Client(params) as client:
            listed = await client.list_tools()
            assert len(listed.tools) == 5
            result = await client.call_tool("search", {"query": "webhook signature"})
            assert "Verifying signatures [n" in text_of(result)
            json.dumps(result.structured_content)

    anyio.run(scenario)


def test_serve_requires_db(tmp_path: Path) -> None:
    assert main(["serve", "--db", str(tmp_path / "missing.db")]) == 2
