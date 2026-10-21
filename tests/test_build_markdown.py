import itertools

from subforest.build import chunk_span, parse_markdown


def test_sections_nest_and_spans_cover_subsections() -> None:
    text = "# Doc\nIntro\n## A\na\n### A1\na1\n## B\nb\n"
    doc = parse_markdown(text)
    a, b = doc.sections
    assert doc.title == "Doc"
    assert text[slice(*doc.body)].strip() == "Intro"
    assert text[slice(*a.span)] == "## A\na\n### A1\na1\n"
    assert text[slice(*a.body)] == "a\n"
    assert [c.title for c in a.children] == ["A1"]
    assert text[slice(*b.span)] == "## B\nb\n"


def test_front_matter_title_wins_over_h1() -> None:
    doc = parse_markdown('---\ntitle: "Front"\nslug: x\n---\n# Heading\nbody\n')
    assert doc.title == "Front"
    assert doc.sections == []


def test_unclosed_front_matter_is_plain_text() -> None:
    assert parse_markdown("---\ntitle: x\n# H\n").title is None


def test_h1_after_content_is_a_section() -> None:
    doc = parse_markdown("Intro first\n# Later\n")
    assert doc.title is None
    assert [s.title for s in doc.sections] == ["Later"]


def test_headings_inside_fences_are_ignored() -> None:
    doc = parse_markdown("# T\n```\n## not a heading\n```\n## Real\n~~~~\n# no\n~~~~\n")
    assert [s.title for s in doc.sections] == ["Real"]


def test_closing_hashes_and_non_headings() -> None:
    doc = parse_markdown("# T\n## Title ##\n#nospace\n####### seven\n")
    assert [s.title for s in doc.sections] == ["Title"]


def test_skipped_levels_nest_under_nearest_shallower() -> None:
    doc = parse_markdown("# T\n### Deep\n## Mid\n#### Deeper\n")
    deep, mid = doc.sections
    assert deep.title == "Deep" and mid.children[0].title == "Deeper"


def test_chunks_stay_inside_span_and_pack_paragraphs() -> None:
    text = "xx\n\npara one\n\npara two\n\n" + "word " * 50 + "\n\nyy"
    ranges = chunk_span(text, 4, len(text) - 4, max_chars=40)
    assert all(4 <= s < e <= len(text) - 4 for s, e in ranges)
    assert text[slice(*ranges[0])] == "para one\n\npara two"
    assert all(e - s <= 40 for s, e in ranges)
    assert all(a[1] <= b[0] for a, b in itertools.pairwise(ranges))


def test_chunk_whitespace_only_is_empty() -> None:
    assert chunk_span("  \n\n \t", 0, 6) == []
