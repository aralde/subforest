import os
from pathlib import Path

import pytest

from subforest import Node, TreeStore
from subforest.build import BuildResult, DocSource, assemble, build_corpus, docs_from_sitemap, scan_directory

SNAPSHOT = Path(__file__).parent / "snapshots" / "fixture_tree.txt"


def outline(result: BuildResult) -> str:
    depth: dict[int | None, int] = {None: -1}
    chunks: dict[int, int] = {}
    for c in result.chunks:
        chunks[c.node_id] = chunks.get(c.node_id, 0) + 1
    lines = []
    for n in result.nodes:
        depth[n.id] = depth[n.parent_id] + 1
        loc = n.path or n.url or ""
        span = f" {n.span[0]}-{n.span[1]}" if n.span else ""
        lines.append(
            f"{'  ' * depth[n.id]}{n.short_id} {n.kind} {n.title!r} {loc}{span} chunks={chunks.get(n.id, 0)}"
        )
    return "\n".join(lines) + "\n"


def test_fixture_tree_matches_snapshot(corpus_dir: Path) -> None:
    got = outline(build_corpus(corpus_dir, corpus_id="larch"))
    if os.environ.get("SUBFOREST_UPDATE_SNAPSHOTS"):
        SNAPSHOT.write_text(got)
    assert got == SNAPSHOT.read_text()


def test_build_is_deterministic(corpus_dir: Path) -> None:
    assert build_corpus(corpus_dir) == build_corpus(corpus_dir)


def test_every_chunk_lies_inside_its_node(corpus_dir: Path) -> None:
    result = build_corpus(corpus_dir)
    nodes = {n.id: n for n in result.nodes}
    for c in result.chunks:
        node = nodes[c.node_id]
        assert node.span is not None and node.span[0] <= c.start <= c.end <= node.span[1]
        children = [n for n in result.nodes if n.parent_id == node.id and n.span]
        assert not any(ch.span and ch.span[0] < c.end and c.start < ch.span[1] for ch in children)


def test_chunk_text_matches_source(corpus_dir: Path) -> None:
    result = build_corpus(corpus_dir)
    nodes = {n.id: n for n in result.nodes}
    for c in result.chunks:
        node = nodes[c.node_id]
        while node.kind != "doc":
            assert node.parent_id is not None
            node = nodes[node.parent_id]
        assert node.path is not None
        assert (corpus_dir / node.path).read_text()[c.start : c.end] == c.text


def test_build_writes_to_store(corpus_dir: Path) -> None:
    result = build_corpus(corpus_dir, corpus_id="larch")
    with TreeStore() as store:
        result.write(store)
        tokens = next(n for n in result.nodes if n.title == "Rotating tokens")
        assert [n.title for n in store.ancestors(tokens.id)] == [
            "larch/",
            "guides/",
            "Authentication",
            "Tokens",
        ]


def test_sitemap_matches_directory_docs(corpus_dir: Path) -> None:
    from_sitemap = build_corpus(corpus_dir / "sitemap.xml", corpus_id="larch")
    site = from_sitemap.nodes[0]
    assert site.url == "https://docs.larch.example/"
    docs = [n for n in from_sitemap.nodes if n.kind == "doc"]
    assert len(docs) == 12 and all(d.path and d.url for d in docs)
    titles = lambda r: sorted(n.title for n in r.nodes if n.kind != "site")  # noqa: E731
    assert titles(from_sitemap) == titles(build_corpus(corpus_dir, corpus_id="larch"))
    guides = next(n for n in from_sitemap.nodes if n.title == "guides/")
    assert guides.url == "https://docs.larch.example/guides/"


def test_sitemap_without_content_keeps_order() -> None:
    xml = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://x.dev/b/two</loc></url><url><loc>https://x.dev/a</loc></url>"
        "<url><loc>https://x.dev/b/one</loc></url><url><loc>https://x.dev/a</loc></url></urlset>"
    )
    result = assemble(docs_from_sitemap(xml), corpus_id="x")
    assert [n.title for n in result.nodes] == ["x/", "b/", "two", "one", "a"]
    assert result.chunks == []


def test_sitemap_rejects_non_urlset() -> None:
    with pytest.raises(ValueError):
        docs_from_sitemap("<sitemapindex/>")


def test_sitemap_content_cannot_escape_root(tmp_path: Path) -> None:
    (tmp_path / "secret.md").write_text("# Secret")
    root = tmp_path / "site"
    root.mkdir()
    xml = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://x.dev/%2E%2E/secret</loc></url></urlset>"
    )
    assert all(d.text is None for d in docs_from_sitemap(xml, content_root=root))


def test_scan_skips_symlinks_out_of_root_and_hidden(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.md").write_text("# Leak")
    root = tmp_path / "root"
    (root / ".hidden").mkdir(parents=True)
    (root / ".hidden" / "h.md").write_text("# H")
    (root / "ok.md").write_text("# OK")
    (root / "notes.txt").write_text("skip")
    (root / "link.md").symlink_to(outside / "leak.md")
    (root / "linkdir").symlink_to(outside, target_is_directory=True)
    assert [d.path for d in scan_directory(root)] == ["ok.md"]


def test_duplicate_documents_rejected() -> None:
    with pytest.raises(ValueError):
        assemble([DocSource(parts=("a",)), DocSource(parts=("a",))], corpus_id="c")


def test_doc_without_title_uses_file_stem() -> None:
    result = assemble([DocSource(parts=("notes.mdx",), path="notes.mdx", text="plain text")], corpus_id="c")
    assert result.nodes[1] == Node(
        id=2, corpus_id="c", parent_id=1, kind="doc", title="notes", path="notes.mdx", span=(0, 10)
    )
