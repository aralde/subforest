"""Parse Markdown/MDX into a section outline with character spans."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_FM_TITLE = re.compile(r"^title[ \t]*:[ \t]*(.+?)[ \t]*$")


@dataclass(frozen=True)
class Section:
    """A heading and the text it governs.

    `span` covers the heading line through the end of its last subsection; `body` covers only the text
    between the heading line and the next heading of any level.
    """

    level: int
    title: str
    span: tuple[int, int]
    body: tuple[int, int]
    children: list[Section] = field(default_factory=list)


@dataclass(frozen=True)
class MarkdownDoc:
    """A parsed document: its title, the text it owns before the first section, and its top-level sections.

    Example:
        >>> doc = parse_markdown("# Auth\\nIntro.\\n## Tokens\\nUse them.\\n")
        >>> doc.title, [s.title for s in doc.sections]
        ('Auth', ['Tokens'])
    """

    title: str | None
    body: tuple[int, int]
    sections: list[Section]


def _front_matter(text: str) -> tuple[str | None, int]:
    if not text.startswith("---\n"):
        return None, 0
    title = None
    pos = 4
    while pos < len(text):
        end = text.find("\n", pos)
        end = len(text) if end == -1 else end
        line = text[pos:end]
        if line in ("---", "..."):
            return title, min(end + 1, len(text))
        if m := _FM_TITLE.match(line):
            title = m.group(1).strip("'\"")
        pos = end + 1
    return None, 0


def _headings(text: str, start: int) -> list[tuple[int, str, int, int]]:
    found = []
    fence: str | None = None
    pos = start
    while pos < len(text):
        end = text.find("\n", pos)
        end = len(text) if end == -1 else end
        line = text[pos:end]
        if m := _FENCE.match(line):
            marker = m.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
        elif fence is None and (m := _HEADING.match(line)):
            found.append((len(m.group(1)), m.group(2), pos, min(end + 1, len(text))))
        pos = end + 1
    return found


def parse_markdown(text: str) -> MarkdownDoc:
    """Parse ATX headings (outside fenced code) into nested sections; read `title:` from front matter.

    A leading level-1 heading becomes the document title and is not a section. The title falls back to
    `None` when there is neither front matter title nor leading H1.

    Example:
        >>> doc = parse_markdown("---\\ntitle: Guide\\n---\\n# Start\\n## A\\n### B\\n## C\\n")
        >>> doc.title, [(s.title, [c.title for c in s.children]) for s in doc.sections]
        ('Guide', [('A', ['B']), ('C', [])])
    """
    fm_title, content_start = _front_matter(text)
    heads = _headings(text, content_start)
    title = fm_title
    body_start = content_start
    if heads and heads[0][0] == 1 and not text[content_start : heads[0][2]].strip():
        title = title or heads[0][1]
        body_start = heads[0][3]
        heads = heads[1:]

    top: list[Section] = []
    stack: list[Section] = []
    for i, (level, head_title, line_start, line_end) in enumerate(heads):
        next_start = heads[i + 1][2] if i + 1 < len(heads) else len(text)
        span_end = next((h[2] for h in heads[i + 1 :] if h[0] <= level), len(text))
        section = Section(level, head_title, (line_start, span_end), (line_end, next_start))
        while stack and stack[-1].level >= level:
            stack.pop()
        (stack[-1].children if stack else top).append(section)
        stack.append(section)

    doc_body_end = heads[0][2] if heads else len(text)
    return MarkdownDoc(title, (body_start, doc_body_end), top)
