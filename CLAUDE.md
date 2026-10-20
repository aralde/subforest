# subforest

Index-agnostic **structural navigation for agentic retrieval**. Given any search index, `subforest` returns the
*retrieval-induced sub-forest* — the document-structure skeleton around the hits — instead of a flat list of
chunks, and lets the agent `expand` / `read` nodes from there.

Independent, MIT-licensed implementation inspired by RIT-RAG (Pulivarthi et al., arXiv:2610.11370). It is NOT the
official implementation; never describe it that way in code, docs or README.

## Why this exists (keep every decision aligned to this)
- Agentic RAG shows the model isolated chunks and loses document structure.
- Structure-only navigation (vectorless / TOC tree search) commits to a path before seeing content and misses recall.
- The paper's key ablation: same index, same model, the only change is what the agent sees after `search`
  (chunks vs. induced sub-forest) → large accuracy gain. **That ablation is our core product and our core eval.**

## Product shape
1. `subforest.build` — offline tree builders (deterministic, no LLM by default):
   - inter-document: `sitemap.xml`, URL path hierarchy, `llms.txt`
   - intra-document: Markdown/MDX headings (PDF outline later)
2. `subforest.retrievers` — adapters behind one `Retriever` protocol. Default: SQLite FTS5 (BM25). Others are optional extras.
3. `subforest.induce` — hits → node set → ancestors → union → budgeted, compact text rendering.
4. `subforest.tools` — agent tools: `search`, `expand`, `read`, `siblings`, `outline`.
5. `subforest.policy` — declarative tool-order rules (e.g. "no semantic search until ≥1 `read` this turn").
6. `subforest.mcp` — MCP server exposing the tools (stdio first).
7. `subforest.eval` — harness: `mode=chunks` vs `mode=subforest`, same retriever, same model.

## Stack and conventions
- Python ≥ 3.11, `uv` for env/deps, `src/` layout, package name `subforest`.
- `ruff` (lint + format), `mypy --strict` on `src/`, `pytest`.
- Core has **zero heavy deps**: stdlib + `sqlite3` + `pydantic`. Embeddings, vector DBs, LLM SDKs and MCP live in
  optional extras (`subforest[mcp]`, `subforest[eval]`, `subforest[pgvector]`, …).
- Typed public API; dataclasses/pydantic models for `Node`, `Chunk`, `Hit`, `SubForest`.
- Tests never touch the network. Use the tiny fixture corpus in `tests/fixtures/corpus/`.
- Tools are **read-only**. Resolve every path against the corpus root; reject traversal (`..`, symlinks out of root).
- Rendering must respect a token budget passed by the caller; collapse instead of truncating mid-node.
- Every public function gets a docstring with a short example.
- Commits: conventional commits (`feat:`, `fix:`, `test:`, `docs:`). Small, one concern each.

## Data model (initial — refine in M0, then keep stable)
- `Node(id, corpus_id, parent_id, kind: site|dir|doc|section, title, url|path, order, span: (start, end) | None)`
- `Chunk(id, node_id, text, start, end)` — every chunk belongs to exactly one leaf-ish node.
- `Hit(chunk_id, node_id, score, rank)`
- `SubForest(roots, nodes, hit_marks)` + `render(budget_tokens) -> str`

## Rendering contract (what the agent sees after `search`)
Indented outline, stable short node ids, hit markers, collapsed siblings. Example:
```
docs/ (site)
  guides/ [n12]
    Authentication [n31] ●●● 3 hits
      Tokens [n33] ● 1 hit
      … +4 sections
  api/ [n50]
    Sessions [n58] ● 1 hit
… 2 more docs with weaker hits (call search with more_results=true)
```
The agent then calls `expand("n31")` or `read("n33")`. `read` returns text with its breadcrumb path.

## Non-goals (MVP)
- No hosted service, no auth, no UI.
- No OCR / PDF parsing beyond outlines.
- No LLM-generated summaries in the tree (optional later, off by default).
- No claim of reproducing the paper's exact numbers.

## How to work in this repo
- Follow `PLAN.md` milestone by milestone. Do not start a milestone before the previous one's acceptance criteria pass.
- Before writing code for a milestone, restate its acceptance criteria and list the files you'll touch.
- After each milestone: run `uv run ruff check . && uv run mypy src && uv run pytest`, update `PLAN.md` checkboxes,
  and commit.
- If a design decision isn't covered here, pick the simplest option, write it in `docs/decisions.md` (one line per
  decision: date, decision, reason) and continue.
- Datasets: check and record each dataset's license in `docs/datasets.md` before downloading or redistributing
  anything. Never commit dataset files; download scripts only.
