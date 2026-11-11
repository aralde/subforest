# subforest

Structural navigation for agentic retrieval. Given any search index, `subforest` returns the
*retrieval-induced sub-forest* — the document-structure skeleton around the hits — instead of a flat list of
chunks, and gives the agent tools to `expand` and `read` nodes from there.

[![CI](https://github.com/aralde/subforest/actions/workflows/ci.yml/badge.svg)](https://github.com/aralde/subforest/actions/workflows/ci.yml)

> Status: alpha (0.1.0, not on PyPI yet). Builders, retrieval, MCP server and evaluation harness work and are
> tested. Sibling project: [ragtrail](https://github.com/aralde/ragtrail), a trajectory cache for agentic RAG that
> can use subforest node ids. The public API may change between 0.x releases.

## Attribution

`subforest` is an independent, MIT-licensed implementation inspired by RIT-RAG
(Pulivarthi et al., [arXiv:2610.11370](https://arxiv.org/abs/2610.11370)). It is not the official implementation
of that paper and does not claim to reproduce its results.

## Install

```bash
pip install 'subforest[mcp,yaml] @ git+https://github.com/aralde/subforest.git'
```

Python 3.11 or newer. The core needs only `pydantic`; `mcp` and `yaml` are optional extras.

## Quick start

```bash
subforest build path/to/markdown-docs --db corpus.db        # or: subforest build site/sitemap.xml --db corpus.db
subforest search "how do I rotate a token" --db corpus.db --budget 300
```

## Use it from Python

```python
from subforest import TreeStore, induce
from subforest.retrievers import FTS5Retriever

with TreeStore("corpus.db") as store:
    hits = FTS5Retriever(store).search("how do I rotate a token", k=10)  # any retriever returning Hits works
    print(induce(store, hits).render(300))  # the sub-forest, rendered within 300 tokens
```

`induce` takes hits from any search index, so you can keep your own retriever and use subforest only for the
structure around the hits.

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

## Evaluation

Summary and details: [`reports/README.md`](reports/README.md). Same retriever (BM25), model, call budget and view
budget in both arms; Haiku agent and Sonnet judge via `claude -p`.

- **Retrieval only, at equal token budgets.** The first view shows the right WixQA document 1.2–2× as often as a
  flat chunk list (57.5% vs 28.0% at 250 tokens). On QASPER papers, when the question names the paper, it locates
  the evidence section 3–15 points more often.
- **Agent runs.** Long, sectioned papers (QASPER, n = 400): evidence found +5.8 points (significant), answers
  correct 57.5% → 61.3% (+3.8, 95% CI −0.5 to +8.0, not significant). Short flat articles (WixQA, n = 200): no
  effect (58.0% → 58.5%).
- **The price:** about 1.5–2 more tool calls and 20–75% more input tokens per question.

The claim these runs support: structure helps find evidence in long structured documents. Answer gains are not
established. Reproduce with `subforest data fetch`, then `subforest bench | coverage | agent` (needs the `claude`
CLI for the agent runs); datasets and licenses are in [`docs/datasets.md`](docs/datasets.md).

## Limitations

- Builders cover Markdown directories and `sitemap.xml` sites; PDFs need outline parsing and are not supported.
- The agent runs use one model (Haiku) and one judge (Sonnet, checked on 40 labels, not human-labelled).
- More structure means more tool calls; on short flat documents it costs more than it returns.

## Development

```bash
uv sync --all-extras
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
