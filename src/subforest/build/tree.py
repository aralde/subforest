"""Assemble document sources into a node tree with chunks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from subforest.build.chunker import chunk_span
from subforest.build.markdown import Section, parse_markdown
from subforest.models import Chunk, Node, NodeKind
from subforest.store import TreeStore


@dataclass(frozen=True)
class DocSource:
    """One document to place in the tree.

    `parts` are the hierarchy segments (directories, then the document name); `text` is the Markdown body,
    or `None` when only the location is known (e.g. a sitemap entry without local content).

    Example:
        >>> DocSource(parts=("guides", "auth.md"), path="guides/auth.md", text="# Auth\\n").parts[-1]
        'auth.md'
    """

    parts: tuple[str, ...]
    path: str | None = None
    url: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class BuildResult:
    """Nodes and chunks produced by a build, ready to write into a `TreeStore`.

    Example:
        >>> result = assemble([DocSource(parts=("a.md",), text="# A\\nHello.\\n")], corpus_id="c")
        >>> [n.title for n in result.nodes], [c.text for c in result.chunks]
        (['c/', 'A'], ['Hello.'])
    """

    nodes: list[Node]
    chunks: list[Chunk]

    def write(self, store: TreeStore) -> None:
        """Insert every node and chunk into `store`.

        Example:
            >>> store = TreeStore()
            >>> assemble([DocSource(parts=("a.md",), text="Hi")], corpus_id="c").write(store)
            >>> store.get_node(2).title
            'a'
        """
        store.add_nodes(self.nodes)
        store.add_chunks(self.chunks)


@dataclass
class _Dir:
    name: str
    path: str
    url: str | None
    entries: dict[tuple[str, str], _Dir | DocSource] = field(default_factory=dict)


def _stem(name: str) -> str:
    return name.rsplit(".", 1)[0] if name.endswith((".md", ".mdx")) else name


class _Emitter:
    def __init__(self, corpus_id: str, max_chunk_chars: int) -> None:
        self.corpus_id = corpus_id
        self.max_chunk_chars = max_chunk_chars
        self.nodes: list[Node] = []
        self.chunks: list[Chunk] = []

    def node(self, parent_id: int | None, kind: NodeKind, title: str, order: int, **kw: object) -> int:
        node_id = len(self.nodes) + 1
        self.nodes.append(
            Node.model_validate(
                {
                    "id": node_id,
                    "corpus_id": self.corpus_id,
                    "parent_id": parent_id,
                    "kind": kind,
                    "title": title,
                    "order": order,
                    **kw,
                }
            )
        )
        return node_id

    def chunk(self, node_id: int, text: str, span: tuple[int, int]) -> None:
        for start, end in chunk_span(text, *span, max_chars=self.max_chunk_chars):
            self.chunks.append(
                Chunk(id=len(self.chunks) + 1, node_id=node_id, text=text[start:end], start=start, end=end)
            )

    def directory(self, d: _Dir, parent_id: int, order: int) -> None:
        node_id = self.node(parent_id, "dir", f"{d.name}/", order, path=d.path or None, url=d.url)
        self.entries(d, node_id)

    def entries(self, d: _Dir, parent_id: int) -> None:
        for order, entry in enumerate(d.entries.values()):
            if isinstance(entry, _Dir):
                self.directory(entry, parent_id, order)
            else:
                self.document(entry, parent_id, order)

    def document(self, doc: DocSource, parent_id: int, order: int) -> None:
        loc = {"path": doc.path, "url": doc.url}
        if doc.text is None:
            self.node(parent_id, "doc", _stem(doc.parts[-1]), order, **loc)
            return
        md = parse_markdown(doc.text)
        title = md.title or _stem(doc.parts[-1])
        node_id = self.node(parent_id, "doc", title, order, span=(0, len(doc.text)), **loc)
        self.chunk(node_id, doc.text, md.body)
        for i, section in enumerate(md.sections):
            self.section(section, doc.text, node_id, i)

    def section(self, s: Section, text: str, parent_id: int, order: int) -> None:
        node_id = self.node(parent_id, "section", s.title, order, span=s.span)
        self.chunk(node_id, text, s.body)
        for i, child in enumerate(s.children):
            self.section(child, text, node_id, i)


def assemble(
    docs: Sequence[DocSource],
    *,
    corpus_id: str,
    site_title: str | None = None,
    site_url: str | None = None,
    max_chunk_chars: int = 1000,
) -> BuildResult:
    """Build a `site → dir → doc → section` tree from document sources, keeping their given order.

    Node and chunk ids are assigned in pre-order starting at 1, so the same input always yields the same
    tree. Directories appear in the order their first document appears.

    Example:
        >>> docs = [DocSource(parts=("api", "notes.md")), DocSource(parts=("faq.md",))]
        >>> [(n.kind, n.title) for n in assemble(docs, corpus_id="c").nodes]
        [('site', 'c/'), ('dir', 'api/'), ('doc', 'notes'), ('doc', 'faq')]
    """
    root = _Dir(name="", path="", url=site_url)
    for doc in docs:
        if not doc.parts:
            raise ValueError("a document needs at least one path segment")
        d = root
        for name in doc.parts[:-1]:
            key = ("dir", name)
            if key not in d.entries:
                url = f"{d.url.rstrip('/')}/{name}/" if d.url else None
                d.entries[key] = _Dir(name=name, path=f"{d.path}/{name}".lstrip("/"), url=url)
            sub = d.entries[key]
            assert isinstance(sub, _Dir)
            d = sub
        key = ("doc", doc.parts[-1])
        if key in d.entries:
            raise ValueError(f"duplicate document {'/'.join(doc.parts)}")
        d.entries[key] = doc

    emit = _Emitter(corpus_id, max_chunk_chars)
    site_id = emit.node(None, "site", site_title or f"{corpus_id}/", 0, url=site_url)
    emit.entries(root, site_id)
    return BuildResult(emit.nodes, emit.chunks)
