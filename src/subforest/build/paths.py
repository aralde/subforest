"""Inter-document hierarchy from a directory tree or from URL paths."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from subforest.build.tree import DocSource

MARKDOWN_SUFFIXES = (".md", ".mdx")


def url_parts(url: str) -> tuple[str, ...]:
    """Split a URL path into hierarchy segments; the site root becomes `("index",)`.

    Example:
        >>> url_parts("https://docs.example.com/guides/auth/")
        ('guides', 'auth')
        >>> url_parts("https://docs.example.com/")
        ('index',)
    """
    parts = tuple(p for p in unquote(urlsplit(url).path).split("/") if p)
    return parts or ("index",)


def resolve_inside(root: Path, relative: str) -> Path | None:
    """Resolve `relative` against `root`, returning `None` if it escapes root (via `..` or symlinks).

    Example:
        >>> resolve_inside(Path("/srv/docs"), "../etc/passwd") is None
        True
    """
    root = root.resolve()
    if PurePosixPath(relative).is_absolute():
        return None
    target = (root / relative).resolve()
    return target if target.is_relative_to(root) else None


def scan_directory(root: Path) -> list[DocSource]:
    """Collect Markdown/MDX files under `root`, sorted by path, skipping hidden entries and escaping symlinks.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmp:
        ...     _ = (Path(tmp) / "a.md").write_text("# A")
        ...     [d.path for d in scan_directory(Path(tmp))]
        ['a.md']
    """
    root = root.resolve()
    found: list[DocSource] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and resolve_inside(root, _rel(root, dirpath, d))
        ]
        for name in filenames:
            if name.startswith(".") or not name.endswith(MARKDOWN_SUFFIXES):
                continue
            rel = _rel(root, dirpath, name)
            target = resolve_inside(root, rel)
            if target is None or not target.is_file():
                continue
            found.append(
                DocSource(parts=tuple(rel.split("/")), path=rel, text=target.read_text(encoding="utf-8"))
            )
    return sorted(found, key=lambda d: d.parts)


def _rel(root: Path, dirpath: str, name: str) -> str:
    return (Path(dirpath) / name).relative_to(root).as_posix()
