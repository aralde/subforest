# subforest

Structural navigation for agentic retrieval. Given any search index, `subforest` returns the
*retrieval-induced sub-forest* — the document-structure skeleton around the hits — instead of a flat list of
chunks, and gives the agent tools to `expand` and `read` nodes from there.

> Status: early development (pre-0.1). Nothing is published yet.

## Attribution

`subforest` is an independent, MIT-licensed implementation inspired by RIT-RAG
(Pulivarthi et al., [arXiv:2610.11370](https://arxiv.org/abs/2610.11370)). It is not the official implementation
of that paper and does not claim to reproduce its results.

## Quick start

```bash
pip install 'subforest[mcp,yaml]'   # not on PyPI yet: use `uv sync --all-extras` in this repo
subforest build path/to/markdown-docs --db corpus.db        # or: subforest build site/sitemap.xml --db corpus.db
subforest search "how do I rotate a token" --db corpus.db --budget 300
```

## Use it from an MCP client

`subforest serve` runs an MCP server over stdio exposing five read-only tools: `search`, `expand`, `read`,
`siblings` and `outline`. An optional policy file sets tool-order rules
(see [`examples/policies/`](examples/policies/)).

**Claude Code**

```bash
claude mcp add subforest -- subforest serve --db /abs/path/corpus.db \
  --policy /abs/path/read-before-semantic-search.yaml
```

**Other clients** (Claude Desktop, Cursor, …) take the same command in their JSON config:

```json
{
  "mcpServers": {
    "subforest": {
      "command": "subforest",
      "args": ["serve", "--db", "/abs/path/corpus.db"]
    }
  }
}
```

MCP has no notion of an agent turn, so policy counters reset after a pause between calls
(`--turn-idle-seconds`, default 120).

## Development

```bash
uv sync --all-extras
uv run ruff check . && uv run mypy src && uv run pytest
```

## License

MIT — see [LICENSE](LICENSE).
