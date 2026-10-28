"""Minimal HTML → Markdown conversion that keeps headings, paragraphs and list items (stdlib only)."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCKS = {"p", "div", "li", "tr", "table", "ul", "ol", "blockquote", "pre", "hr", "section", "summary"}
_SKIP = {"script", "style", "noscript", "svg"}
_SPACES = re.compile("[ \t\xa0]+")


class _Converter(HTMLParser):
    def __init__(self, shift: int) -> None:
        super().__init__(convert_charrefs=True)
        self.shift = shift
        self.blocks: list[str] = []
        self.current: list[str] = []
        self.heading: int | None = None
        self.skip = 0

    def flush(self) -> None:
        text = _SPACES.sub(" ", "".join(self.current)).strip()
        self.current = []
        if not text:
            return
        if self.heading is not None:
            level = min(self.heading + self.shift, 6)
            self.blocks.append(f"{'#' * level} {' '.join(text.split())}")
        else:
            lines = [line.strip() for line in text.split("\n")]
            self.blocks.append("\n".join(line for line in lines if line))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self.skip += 1
        elif tag in _HEADINGS:
            self.flush()
            self.heading = _HEADINGS[tag]
        elif tag in _BLOCKS:
            self.flush()
            if tag == "li":
                self.current.append("- ")
        elif tag == "br":
            self.current.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in _HEADINGS:
            self.flush()
            self.heading = None
        elif tag in _BLOCKS:
            self.flush()

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.current.append(data)


def html_to_markdown(html: str, *, heading_shift: int = 0) -> str:
    """Convert HTML to Markdown with ATX headings, one blank line between blocks; drops images and scripts.

    `heading_shift` pushes every heading down (e.g. 1 turns `<h2>` into `###`), leaving room for a title.

    Example:
        >>> print(html_to_markdown("<h2>Setup</h2><div>Click <b>Save</b>.</div><ul><li>One</li></ul>"))
        ## Setup
        <BLANKLINE>
        Click Save.
        <BLANKLINE>
        - One
    """
    converter = _Converter(heading_shift)
    converter.feed(html)
    converter.close()
    converter.flush()
    return "\n\n".join(converter.blocks)
