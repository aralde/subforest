# subforest

Structural navigation for agentic retrieval. Given any search index, `subforest` returns the
*retrieval-induced sub-forest* — the document-structure skeleton around the hits — instead of a flat list of
chunks, and gives the agent tools to `expand` and `read` nodes from there.

> Status: early development (pre-0.1). Nothing is published yet.

## Attribution

`subforest` is an independent, MIT-licensed implementation inspired by RIT-RAG
(Pulivarthi et al., [arXiv:2610.11370](https://arxiv.org/abs/2610.11370)). It is not the official implementation
of that paper and does not claim to reproduce its results.

## Development

```bash
uv sync
uv run ruff check . && uv run mypy src && uv run pytest
```

## License

MIT — see [LICENSE](LICENSE).
