# subforest — plan

Status legend: `[ ]` pending · `[x]` done. Update as you go.

## M0 — Scaffold and data model
- [x] `uv init --lib`, `src/subforest/`, MIT `LICENSE` (holder: Ariel / aralde), `README.md` stub with paper attribution
- [x] ruff, mypy strict, pytest configured; GitHub Actions CI (lint, types, tests on 3.11 and 3.12)
- [x] Models: `Node`, `Chunk`, `Hit`, `SubForest` (pydantic) + `TreeStore` on SQLite (nodes table, closure or
      parent-pointer + recursive CTE for ancestors)
- [x] Fixture corpus in `tests/fixtures/corpus/`: ~12 Markdown files across 3 folders + a `sitemap.xml`
- [x] Confirm `subforest` is free on PyPI (`pip index versions subforest`); if taken, stop and report

**Accept:** CI green; `TreeStore.ancestors(node_id)` tested.

_Status: all checks pass locally on 3.11 and 3.12; CI runs on GitHub once the remote exists._

## M1 — Tree builders
- [x] `build.markdown`: headings → section nodes with character spans; front-matter title support
- [x] `build.paths`: directory / URL path hierarchy → inter-doc nodes
- [x] `build.sitemap`: parse `sitemap.xml` into the same hierarchy
- [x] Chunker: split section bodies into chunks that never cross a section boundary
- [x] CLI: `subforest build <path|sitemap-url-file> --db corpus.db`

**Accept:** building the fixture corpus yields a deterministic tree (snapshot test).

_Status: done — `tests/snapshots/fixture_tree.txt`; regenerate with `SUBFOREST_UPDATE_SNAPSHOTS=1`._

## M2 — Retrieval + induction (the core)
- [ ] `Retriever` protocol: `search(query, k) -> list[Hit]`
- [ ] `retrievers.fts5`: SQLite FTS5 BM25 over chunks (default)
- [ ] `induce(hits) -> SubForest`: map hits → nodes, add ancestors, union across docs, aggregate hit counts/scores
- [ ] `render(subforest, budget_tokens)`: rendering contract from `CLAUDE.md`; collapse low-signal siblings first,
      then whole weak docs; never cut a line mid-node
- [ ] Token estimator: simple heuristic by default, pluggable

**Accept:** golden-file tests for render at 3 budgets; induced forest always contains every hit's ancestors.

## M3 — Agent tools + policy layer
- [ ] Tools: `search(query, more_results=False)`, `expand(node_id, depth=1)`, `read(node_id, max_tokens)`,
      `siblings(node_id)`, `outline(doc_id)`; all return text + structured payload
- [ ] `policy`: YAML/dict rules evaluated against per-turn state. Rule types for MVP:
      `require_before` (tool A needs ≥N calls of tool B in scope), `max_calls`, `cooldown`.
      Violations return a short, instructive message instead of executing.
- [ ] Example policy file reproducing "read before semantic search"
- [ ] Path-safety tests (traversal, symlink escape)

**Accept:** a scripted fake agent run exercises every tool and one blocked call.

## M4 — MCP server
- [ ] `subforest[mcp]` extra; stdio server exposing the M3 tools; `subforest serve --db corpus.db --policy p.yaml`
- [ ] README snippet for adding it to Claude Code (`claude mcp add …`) and other MCP clients
- [ ] Manual smoke test against the fixture corpus from a real MCP client; record result in `docs/decisions.md`

**Accept:** tools listed and callable from an MCP client.

## M5 — Eval harness (the headline)
- [ ] `docs/datasets.md`: licenses for WixQA, QASPER, FinanceBench; pick the first one that allows local use
- [ ] Download script (no data committed) + loader into `TreeStore`
- [ ] Agent loop with pluggable LLM provider (Anthropic default via `subforest[eval]`)
- [ ] Two arms, identical retriever and model: `chunks` (top-k chunk texts) vs `subforest` (induced view + tools)
- [ ] Metrics: answer accuracy (LLM judge, prompt in repo), tokens in/out, tool calls, latency; JSONL logs per run
- [ ] `subforest eval --dataset wixqa --arm both --n 100` → markdown report in `reports/`

**Accept:** a reproducible run on ≥100 questions with both arms and a report table.

## M6 — Release
- [ ] README: problem, 30-second demo, eval table, honest limitations, attribution to the paper
- [ ] `v0.1.0` on PyPI, GitHub release, tag

## Later (not MVP)
- Embedding / hybrid retrievers (pgvector, Pinecone, Qdrant) behind extras
- PDF outlines; HTML heading extraction for crawled sites
- Optional LLM node summaries
- TypeScript port of the tool layer
