# Decisions

One line per decision: date — decision — reason.

- 2026-10-20 — Node and chunk ids are integers; agents see them as `n<id>` (`Node.short_id`) — simplest stable short id that maps 1:1 to the SQLite primary key.
- 2026-10-20 — `TreeStore` uses parent pointers + a recursive CTE for ancestors (no closure table) — trees are shallow and writes stay trivial; revisit only if ancestor queries show up in profiles.
- 2026-10-20 — `ancestors()` returns root → parent, excluding the node itself — matches the breadcrumb order `read` will print.
- 2026-10-20 — Models are frozen pydantic models with `extra="forbid"` — immutable values are safe to share between store, induction and tools.
- 2026-10-20 — Docstring examples run as doctests (`--doctest-modules`) — keeps the "every public function has an example" rule honest.
- 2026-10-20 — Fixture corpus describes a fictional product ("Larch") — no third-party content, no license questions.
