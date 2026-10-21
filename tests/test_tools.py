from collections.abc import Iterator
from pathlib import Path

import pytest

from subforest import TreeStore
from subforest.build import build_corpus
from subforest.policy import Policy
from subforest.retrievers import FTS5Retriever
from subforest.tools import Toolkit, ToolResult, parse_node_id


@pytest.fixture
def tools(corpus_dir: Path) -> Iterator[Toolkit]:
    with TreeStore() as store:
        build_corpus(corpus_dir, corpus_id="docs").write(store)
        yield Toolkit(store, FTS5Retriever(store), budget_tokens=200)


def node_id(tools: Toolkit, title: str) -> str:
    row = tools.store.connection.execute("SELECT id FROM nodes WHERE title = ?", (title,)).fetchone()
    return f"n{row[0]}"


def test_search_returns_forest_and_payload(tools: Toolkit) -> None:
    result = tools.call("search", query="webhook signature")
    assert not result.error
    assert "Verifying signatures [n" in result.text
    assert result.data["hits"][0]["rank"] == 1
    assert result.data["hits"][0]["node"] in result.data["nodes"]


def test_search_more_results_widens(tools: Toolkit) -> None:
    narrow = tools.search("notes")
    wide = tools.search("notes", more_results=True)
    assert len(wide.data["hits"]) > len(narrow.data["hits"])


def test_search_empty_query_is_error(tools: Toolkit) -> None:
    assert tools.call("search", query="  ").error


def test_expand_shows_children_with_hit_marks(tools: Toolkit) -> None:
    tools.call("search", query="token rotate")
    auth = node_id(tools, "Authentication")
    result = tools.call("expand", node_id=auth)
    lines = result.text.splitlines()
    assert lines[0] == f"docs/ › guides/ › Authentication [{auth}]"
    assert any(line.startswith("  Tokens [n") and "hit" in line and "(+1)" in line for line in lines)
    assert [c["title"] for c in result.data["children"]] == ["Tokens", "OAuth", "Scopes", "Troubleshooting"]


def test_expand_depth_two_and_budget_shrinks_depth(tools: Toolkit) -> None:
    tools.budget_tokens = 2000
    deep = tools.call("expand", node_id="n1", depth=5)
    assert deep.data["depth"] == 5 and "Rotating tokens" in deep.text
    tools.budget_tokens = 40
    assert tools.call("expand", node_id="n1", depth=5).data["depth"] < 5


def test_outline_accepts_doc_path(tools: Toolkit) -> None:
    result = tools.call("outline", doc_id="guides/authentication.md")
    assert "    Rotating tokens [n" in result.text
    assert result.data["node"]["title"] == "Authentication"


def test_siblings_marks_current(tools: Toolkit) -> None:
    oauth = node_id(tools, "OAuth")
    result = tools.call("siblings", node_id=oauth)
    assert f"▸ OAuth [{oauth}]" in result.text.splitlines()
    assert len(result.data["siblings"]) == 4
    assert tools.call("siblings", node_id="n1").text.startswith("(top level)")


def test_read_section_includes_heading_and_breadcrumb(tools: Toolkit) -> None:
    tokens = node_id(tools, "Tokens")
    result = tools.call("read", node_id=tokens)
    assert result.text.startswith(f"docs/ › guides/ › Authentication › Tokens [{tokens}]\n\n## Tokens\n")
    assert "### Rotating tokens" in result.text and result.data["complete"]


def test_read_collapses_children_when_too_long(tools: Toolkit) -> None:
    auth = node_id(tools, "Authentication")
    result = tools.call("read", node_id=auth, max_tokens=80)
    assert not result.data["complete"]
    assert "Subsections (read them separately):\n- Tokens [n" in result.text
    assert "## OAuth" not in result.text


def test_read_cuts_at_paragraph_when_own_text_too_long(tools: Toolkit) -> None:
    auth = node_id(tools, "Authentication")
    result = tools.call("read", node_id=auth, max_tokens=50)
    assert "[cut to fit max_tokens" in result.text
    assert tools.estimate(result.text) <= 50 or "Every API request" not in result.text


def test_read_dir_is_error(tools: Toolkit) -> None:
    assert "no readable text" in tools.call("read", node_id="n1").text


@pytest.mark.parametrize(
    "ref",
    ["../etc/passwd", "/etc/passwd", "guides/../../secret.md", "~/x.md", "C:/x.md", "nope", "n99999", "n-1"],
)
def test_bad_references_are_rejected_without_touching_files(tools: Toolkit, ref: str) -> None:
    for tool, arg in [
        ("read", "node_id"),
        ("outline", "doc_id"),
        ("expand", "node_id"),
        ("siblings", "node_id"),
    ]:
        result = tools.call(tool, **{arg: ref})
        assert result.error, (tool, ref)


def test_symlinked_file_outside_root_is_never_readable(tmp_path: Path) -> None:
    (tmp_path / "secret.md").write_text("# Secret\nhunter2\n")
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "ok.md").write_text("# OK\nfine\n")
    (root / "leak.md").symlink_to(tmp_path / "secret.md")
    with TreeStore() as store:
        build_corpus(root).write(store)
        tools = Toolkit(store, FTS5Retriever(store))
        assert tools.call("search", query="hunter2").data["hits"] == []
        assert tools.call("outline", doc_id="leak.md").error
        assert all("hunter2" not in (store.doc_text(i) or "") for i in range(1, 10))


def test_unknown_tool_and_bad_arguments(tools: Toolkit) -> None:
    assert tools.call("rm", path="/").error
    assert "Bad arguments" in tools.call("read", nodeid="n1").text


def test_parse_node_id_rejects_bool_and_junk() -> None:
    assert parse_node_id("n12") == 12
    with pytest.raises(Exception, match="Invalid node id"):
        parse_node_id("twelve")


def test_policy_blocks_and_does_not_execute(tools: Toolkit) -> None:
    tools.state.policy = Policy.from_dict({"rules": [{"type": "max_calls", "tool": "search", "limit": 1}]})
    assert not tools.call("search", query="token").blocked
    blocked = tools.call("search", query="sessions")
    assert blocked.blocked and blocked.data == {"blocked_by_policy": True}
    tools.new_turn()
    assert not tools.call("search", query="sessions").blocked


def test_extra_tools_are_policed(tools: Toolkit) -> None:
    calls: list[str] = []

    def semantic_search(query: str) -> ToolResult:
        calls.append(query)
        return ToolResult(text="semantic results")

    toolkit = Toolkit(
        tools.store,
        tools.retriever,
        policy=Policy.from_dict(
            {"rules": [{"type": "require_before", "tool": "semantic_search", "requires": "read"}]}
        ),
        extra_tools={"semantic_search": semantic_search},
    )
    assert toolkit.call("semantic_search", query="q").blocked and calls == []
    assert "semantic_search" in toolkit.names
