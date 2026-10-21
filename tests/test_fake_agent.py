"""M3 acceptance: a scripted fake agent exercises every tool and hits one policy block."""

import re
from pathlib import Path

from subforest import TreeStore
from subforest.build import build_corpus
from subforest.policy import Policy
from subforest.retrievers import FTS5Retriever
from subforest.tools import TOOL_NAMES, Toolkit, ToolResult

POLICY = Path(__file__).parents[1] / "examples" / "policies" / "read-before-semantic-search.yaml"


def first_id(text: str, title: str) -> str:
    m = re.search(rf"{re.escape(title)} \[(n\d+)\]", text)
    assert m, f"{title!r} not in:\n{text}"
    return m.group(1)


def test_scripted_agent_run(corpus_dir: Path) -> None:
    with TreeStore() as store:
        build_corpus(corpus_dir, corpus_id="docs").write(store)
        tools = Toolkit(
            store,
            FTS5Retriever(store),
            policy=Policy.load(POLICY),
            budget_tokens=250,
            extra_tools={
                "semantic_search": lambda query: ToolResult(text=f"(semantic results for {query!r})")
            },
        )
        log: list[tuple[str, ToolResult]] = []

        def step(name: str, **args: object) -> ToolResult:
            result = tools.call(name, **args)
            log.append((name, result))
            return result

        # Question: "How long do API tokens last, and how do I rotate one?"
        tools.new_turn()
        found = step("search", query="how long do API tokens last and how to rotate")
        auth = first_id(found.text, "Authentication")

        blocked = step("semantic_search", query="token lifetime")
        assert blocked.blocked and "read at least one node" in blocked.text

        again = step("search", query="token rotation")
        assert again.blocked and "since its last use" in again.text

        expanded = step("expand", node_id=auth)
        tokens = first_id(expanded.text, "Tokens")
        step("outline", doc_id="guides/authentication.md")
        step("siblings", node_id=tokens)
        answer_source = step("read", node_id=tokens)
        assert "expire after 90 days" in answer_source.text
        assert "Create a new token, deploy it, then revoke the old one" in answer_source.text

        allowed = step("semantic_search", query="token lifetime")
        assert not allowed.blocked

        executed = {name for name, r in log if not r.blocked and not r.error}
        assert set(TOOL_NAMES) <= executed
        assert [name for name, r in log if r.blocked] == ["semantic_search", "search"]
        assert tools.state.calls == ["search", "expand", "outline", "siblings", "read", "semantic_search"]
