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
- [x] `Retriever` protocol: `search(query, k) -> list[Hit]`
- [x] `retrievers.fts5`: SQLite FTS5 BM25 over chunks (default)
- [x] `induce(hits) -> SubForest`: map hits → nodes, add ancestors, union across docs, aggregate hit counts/scores
- [x] `render(subforest, budget_tokens)`: rendering contract from `CLAUDE.md`; collapse low-signal siblings first,
      then whole weak docs; never cut a line mid-node
- [x] Token estimator: simple heuristic by default, pluggable

**Accept:** golden-file tests for render at 3 budgets; induced forest always contains every hit's ancestors.

_Status: done — goldens in `tests/snapshots/render_{400,120,60}.txt`; try it with `subforest search`._

## M3 — Agent tools + policy layer
- [x] Tools: `search(query, more_results=False)`, `expand(node_id, depth=1)`, `read(node_id, max_tokens)`,
      `siblings(node_id)`, `outline(doc_id)`; all return text + structured payload
- [x] `policy`: YAML/dict rules evaluated against per-turn state. Rule types for MVP:
      `require_before` (tool A needs ≥N calls of tool B in scope), `max_calls`, `cooldown`.
      Violations return a short, instructive message instead of executing.
- [x] Example policy file reproducing "read before semantic search"
- [x] Path-safety tests (traversal, symlink escape)

**Accept:** a scripted fake agent run exercises every tool and one blocked call.

_Status: done — `tests/test_fake_agent.py` (two blocked calls: require_before and cooldown)._

## M4 — MCP server
- [x] `subforest[mcp]` extra; stdio server exposing the M3 tools; `subforest serve --db corpus.db --policy p.yaml`
- [x] README snippet for adding it to Claude Code (`claude mcp add …`) and other MCP clients
- [x] Manual smoke test against the fixture corpus from a real MCP client; record result in `docs/decisions.md`

**Accept:** tools listed and callable from an MCP client.

_Status: done — `tests/test_mcp.py` (in-process and stdio subprocess) + Claude Code smoke test in `docs/decisions.md`._

## M5 — Eval harness (the headline)
The approach itself is validated in the RIT-RAG paper (chunks → sub-forest: +4.5 to +10.5 points on WixQA,
+2.4 to +3.5 on QASPER, same retriever/model/10-call budget). Our job is to check that **this implementation** shows
the effect under our conditions (BM25, current Claude models, MCP), not to re-run the paper. Cheapest first.

Reference settings from the paper: ≤10 tool calls per question, ~50 nodes in the induced view.

### Tier 1 — Scale (no LLM)
- [x] `docs/datasets.md`: licenses for WixQA (MIT) and QASPER (CC BY 4.0); FinanceBench later (long PDFs, out of MVP)
- [x] `subforest data fetch wixqa|qasper`: download (no data committed) + build `corpus.db` and normalized questions
- [x] `subforest bench <dataset>`: build time, DB size, p50/p95 latency of search / induce / render; two builds
      produce identical databases

### Tier 2 — Evidence coverage (no LLM)
- [x] `subforest coverage <dataset>`: at equal token budgets, does the first view contain the gold evidence?
      `chunks` (top-k texts) vs `subforest` (rendered view, evidence reachable with one `read`)
- [x] Reports in `reports/`; if subforest does not beat chunks here, fix rendering before tier 3

_Status: tiers 1–2 done, gate passed — see `reports/README.md`._

### Tier 3 — Agent replication (no spend: Claude subscription via `claude -p`)
- [x] Runner over `claude -p` (Haiku, no built-in tools, only `subforest serve` as MCP), one process per run,
      `runs.jsonl` resumable, stops cleanly at the subscription usage limit
- [x] Two arms, identical retriever, model, call budget (10) and view budget (800 tokens): `chunks` vs `subforest`
- [x] Metrics without an LLM judge: saw gold-doc text, gold doc shown, answer token F1, calls, tokens, latency;
      paired sign test and bootstrap CI
- [x] Pilot: 10 questions to debug the loop (fixed a metric that favoured subforest)
- [x] Pilot: 50 WixQA questions, both arms; report in `reports/` (no gain)
- [x] Pilot: 50 QASPER questions, titled, one per paper (evidence seen +22 points, p = 0.013)
- [x] Full runs on the subscription: WixQA 200 (correct 58.0 → 58.5%, n.s.) and QASPER 400 titled
      (evidence +5.8 points, p = 0.013; correct 57.5 → 61.3%, p = 0.12); `scripts/tier3-full.sh`
- [x] Subscription judge, blind to the arm, checked on 40 labelled answers (Sonnet 97.5%, Haiku 77.5%):
      answers tied in both pilots (WixQA 72 vs 70%, QASPER 52 vs 52%)
- Dropped for now: API runner, paid judge, QASPER and Sonnet confirmation (owner chose zero spend)

### Tier 4 — Dogfooding (qualitative, the corporate argument)
- [ ] Run the MCP server from Claude Code on a real docs corpus (ours or a prospect's) with 50–100 questions written
      by people who know it; note findings in `docs/decisions.md`

**Accept:** WixQA report with both arms, paired significance and confidence intervals.
Stop rule: if subforest does not beat chunks beyond the CI after a couple of render iterations, do not publish an
accuracy claim; document the result honestly.

## M6 — Release
- [ ] README: problem, 30-second demo, eval table, honest limitations, attribution to the paper
- [ ] `v0.1.0` on PyPI, GitHub release, tag

## Later (not MVP)
- Embedding / hybrid retrievers (pgvector, Pinecone, Qdrant) behind extras
- PDF outlines; HTML heading extraction for crawled sites
- Optional LLM node summaries
- TypeScript port of the tool layer
