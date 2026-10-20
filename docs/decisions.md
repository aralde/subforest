# Decisions

One line per decision: date — decision — reason.

- 2026-10-20 — Node and chunk ids are integers; agents see them as `n<id>` (`Node.short_id`) — simplest stable short id that maps 1:1 to the SQLite primary key.
- 2026-10-20 — `TreeStore` uses parent pointers + a recursive CTE for ancestors (no closure table) — trees are shallow and writes stay trivial; revisit only if ancestor queries show up in profiles.
- 2026-10-20 — `ancestors()` returns root → parent, excluding the node itself — matches the breadcrumb order `read` will print.
- 2026-10-20 — Models are frozen pydantic models with `extra="forbid"` — immutable values are safe to share between store, induction and tools.
- 2026-10-20 — Docstring examples run as doctests (`--doctest-modules`) — keeps the "every public function has an example" rule honest.
- 2026-10-20 — Fixture corpus describes a fictional product ("Larch") — no third-party content, no license questions.
- 2026-10-20 — A leading H1 (no content before it) becomes the doc title and is not a section; front-matter `title:` wins over it — avoids a doc whose only child is a section repeating its name.
- 2026-10-20 — Front matter is parsed for `title:` only, without a YAML dependency — keeps the core dependency-free; revisit if more keys matter.
- 2026-10-20 — Only ATX headings (`#`) are parsed; setext headings and headings inside fenced code are ignored — ATX covers the docs sites we target and keeps the parser small.
- 2026-10-20 — Chunk `start`/`end` are offsets into the whole document; each node only chunks the text between its heading and its first child heading — chunks never cross a section boundary by construction.
- 2026-10-20 — Chunks pack whole paragraphs up to `max_chunk_chars` (default 1000), hard-splitting longer paragraphs at the last space — simple, deterministic, no tokenizer dependency.
- 2026-10-20 — Directory builds sort entries by path; sitemap builds keep sitemap order — the sitemap order is the author's intended order, the filesystem has none.
- 2026-10-20 — Sitemap docs read text from `<path>.md|.mdx` or `<path>/index.md|.mdx` next to the sitemap, resolved inside that root — offline builds, no fetching, no path escape.
- 2026-10-20 — `subforest build` refuses an existing `--db` unless `--force` (which replaces it) — no silent merges of two builds into one database.
- 2026-10-20 — `llms.txt` builder deferred (listed in CLAUDE.md, not in M1's plan) — will add when a target corpus needs it.
