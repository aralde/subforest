# Contributing

Issues and pull requests are welcome.

```bash
uv sync --all-extras
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
```

- Tests run offline; they never call the network or a model.
- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`), one concern per commit.
- A decision that changes behavior gets one line in [`docs/decisions.md`](docs/decisions.md).
