"""Split a span of text into chunks that stay inside it."""

from __future__ import annotations

import re

_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")


def _trim(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def _hard_split(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    out = []
    while end - start > max_chars:
        cut = text.rfind(" ", start + 1, start + max_chars + 1)
        cut = start + max_chars if cut == -1 else cut
        if piece := _trim(text, start, cut):
            out.append(piece)
        start = cut
    if piece := _trim(text, start, end):
        out.append(piece)
    return out


def chunk_span(text: str, start: int, end: int, max_chars: int = 1000) -> list[tuple[int, int]]:
    """Return `(start, end)` ranges inside `text[start:end]`, packed by paragraph up to `max_chars`.

    Ranges are trimmed of surrounding whitespace, never overlap and never leave the given span. Paragraphs
    longer than `max_chars` are split at the last space before the limit.

    Example:
        >>> text = "One.\\n\\nTwo.\\n\\nThree is longer."
        >>> [text[s:e] for s, e in chunk_span(text, 0, len(text), max_chars=12)]
        ['One.\\n\\nTwo.', 'Three is', 'longer.']
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    paragraphs = []
    pos = start
    for m in _PARAGRAPH_BREAK.finditer(text, start, end):
        if piece := _trim(text, pos, m.start()):
            paragraphs.append(piece)
        pos = m.end()
    if piece := _trim(text, pos, end):
        paragraphs.append(piece)

    chunks: list[tuple[int, int]] = []
    current: tuple[int, int] | None = None
    for p_start, p_end in paragraphs:
        if current and p_end - current[0] <= max_chars:
            current = (current[0], p_end)
            continue
        if current:
            chunks.append(current)
            current = None
        if p_end - p_start <= max_chars:
            current = (p_start, p_end)
        else:
            chunks.extend(_hard_split(text, p_start, p_end, max_chars))
    if current:
        chunks.append(current)
    return chunks
