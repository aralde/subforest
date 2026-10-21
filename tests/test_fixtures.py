from pathlib import Path
from xml.etree import ElementTree


def test_corpus_shape(corpus_dir: Path) -> None:
    docs = sorted(p.relative_to(corpus_dir).as_posix() for p in corpus_dir.rglob("*.md"))
    assert len(docs) == 12
    assert {d.split("/")[0] for d in docs} == {"guides", "api", "faq"}


def test_sitemap_lists_every_doc(corpus_dir: Path) -> None:
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text for e in ElementTree.parse(corpus_dir / "sitemap.xml").findall("sm:url/sm:loc", ns)]
    paths = {loc.removeprefix("https://docs.larch.example/") + ".md" for loc in locs if loc}
    assert paths == {p.relative_to(corpus_dir).as_posix() for p in corpus_dir.rglob("*.md")}
