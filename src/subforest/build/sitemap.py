"""Inter-document hierarchy from a `sitemap.xml`."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

from subforest.build.paths import MARKDOWN_SUFFIXES, resolve_inside, url_parts
from subforest.build.tree import DocSource

_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def sitemap_urls(xml: str) -> list[str]:
    """Return the `<loc>` URLs of a sitemap `urlset`, in document order, without duplicates.

    Example:
        >>> sitemap_urls('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        ...              '<url><loc> https://x.dev/a </loc></url></urlset>')
        ['https://x.dev/a']
    """
    root = ElementTree.fromstring(xml)
    if root.tag != f"{_NS}urlset":
        raise ValueError(f"expected a sitemap <urlset>, got <{root.tag}>")
    urls = [(loc.text or "").strip() for loc in root.iter(f"{_NS}loc")]
    return list(dict.fromkeys(u for u in urls if u))


def site_url(urls: list[str]) -> str | None:
    """Return the `scheme://host/` shared by the URLs, or `None` if they span several hosts.

    Example:
        >>> site_url(["https://x.dev/a", "https://x.dev/b/c"])
        'https://x.dev/'
    """
    bases = {f"{p.scheme}://{p.netloc}/" for p in map(urlsplit, urls)}
    return bases.pop() if len(bases) == 1 else None


def docs_from_sitemap(xml: str, content_root: Path | None = None) -> list[DocSource]:
    """Turn sitemap URLs into document sources, in sitemap order.

    With `content_root`, each URL path `p` is matched to a local `p.md`, `p.mdx`, `p/index.md` or
    `p/index.mdx` inside the root (never outside it) and its text is attached.

    Example:
        >>> xml = ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        ...        '<url><loc>https://x.dev/api/notes</loc></url></urlset>')
        >>> [(d.parts, d.url, d.text) for d in docs_from_sitemap(xml)]
        [(('api', 'notes'), 'https://x.dev/api/notes', None)]
    """
    docs = []
    for url in sitemap_urls(xml):
        parts = url_parts(url)
        path, text = None, None
        if content_root is not None:
            for candidate in _candidates("/".join(parts)):
                target = resolve_inside(content_root, candidate)
                if target is not None and target.is_file():
                    path, text = candidate, target.read_text(encoding="utf-8")
                    break
        docs.append(DocSource(parts=parts, path=path, url=url, text=text))
    return docs


def _candidates(rel: str) -> list[str]:
    if rel.endswith(MARKDOWN_SUFFIXES):
        return [rel]
    return [rel + s for s in MARKDOWN_SUFFIXES] + [f"{rel}/index{s}" for s in MARKDOWN_SUFFIXES]
