"""Offline, deterministic tree builders: directories, URL paths, sitemaps and Markdown headings."""

from __future__ import annotations

from pathlib import Path

from subforest.build.chunker import chunk_span
from subforest.build.markdown import MarkdownDoc, Section, parse_markdown
from subforest.build.paths import scan_directory, url_parts
from subforest.build.sitemap import docs_from_sitemap, site_url, sitemap_urls
from subforest.build.tree import BuildResult, DocSource, assemble

__all__ = [
    "BuildResult",
    "DocSource",
    "MarkdownDoc",
    "Section",
    "assemble",
    "build_corpus",
    "chunk_span",
    "docs_from_sitemap",
    "parse_markdown",
    "scan_directory",
    "site_url",
    "sitemap_urls",
    "url_parts",
]


def build_corpus(source: Path, *, corpus_id: str | None = None, max_chunk_chars: int = 1000) -> BuildResult:
    """Build a tree from a directory of Markdown files or from a local `sitemap.xml`.

    For a sitemap, document text is read from Markdown files next to it when their paths match.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmp:
        ...     _ = (Path(tmp) / "a.md").write_text("# A\\n## B\\nText")
        ...     [n.title for n in build_corpus(Path(tmp), corpus_id="c").nodes]
        ['c/', 'A', 'B']
    """
    if source.is_dir():
        cid = corpus_id or source.resolve().name
        docs = scan_directory(source)
        return assemble(docs, corpus_id=cid, max_chunk_chars=max_chunk_chars)
    xml = source.read_text(encoding="utf-8")
    base = site_url(sitemap_urls(xml))
    cid = corpus_id or source.resolve().parent.name
    docs = docs_from_sitemap(xml, content_root=source.parent)
    return assemble(docs, corpus_id=cid, site_url=base, max_chunk_chars=max_chunk_chars)
