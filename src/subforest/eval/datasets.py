"""Download public QA datasets and build a `corpus.db` plus normalized questions (no data in the repo).

Layout under the data root (default `~/.cache/subforest/datasets`, or `$SUBFOREST_DATA`):

    <root>/<dataset>/raw/...           downloaded files, untouched
    <root>/<dataset>/corpus.db         tree + chunks + FTS index
    <root>/<dataset>/questions.jsonl   one `Question` per line
"""

from __future__ import annotations

import ast
import json
import os
import re
import tarfile
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from subforest.build import BuildResult, DocSource, assemble
from subforest.eval.html import html_to_markdown
from subforest.models import Node
from subforest.retrievers import FTS5Retriever
from subforest.store import TreeStore

WIXQA_BASE = "https://huggingface.co/datasets/Wix/WixQA/resolve/main"
QASPER_TEST = "https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-test-and-evaluator-v0.3.tgz"

Downloader = Callable[[str, Path], None]


class GoldSpan(BaseModel):
    """A piece of gold evidence: character range inside a document node's text."""

    doc: int
    start: int
    end: int


class Question(BaseModel):
    """A normalized eval question with its gold documents (node ids) and, when known, gold evidence spans.

    Example:
        >>> Question(id="q1", question="How?", answer="Like this.", gold_docs=[2]).gold_spans
        []
    """

    id: str
    question: str
    answer: str
    gold_docs: list[int]
    gold_spans: list[GoldSpan] = Field(default_factory=list)
    context: str | None = None


@dataclass(frozen=True)
class Dataset:
    """A dataset's on-disk location.

    Example:
        >>> Dataset("wixqa", Path("/data")).db
        PosixPath('/data/wixqa/corpus.db')
    """

    name: str
    root: Path

    @property
    def dir(self) -> Path:
        return self.root / self.name

    @property
    def raw(self) -> Path:
        return self.dir / "raw"

    @property
    def db(self) -> Path:
        return self.dir / "corpus.db"

    @property
    def questions_path(self) -> Path:
        return self.dir / "questions.jsonl"

    def questions(self) -> list[Question]:
        """Load the normalized questions (after `fetch`)."""
        with self.questions_path.open(encoding="utf-8") as f:
            return [Question.model_validate_json(line) for line in f if line.strip()]


def data_root() -> Path:
    """Return `$SUBFOREST_DATA` or `~/.cache/subforest/datasets`.

    Example:
        >>> isinstance(data_root(), Path)
        True
    """
    env = os.environ.get("SUBFOREST_DATA")
    return Path(env).expanduser() if env else Path.home() / ".cache" / "subforest" / "datasets"


def http_download(url: str, dest: Path) -> None:  # pragma: no cover - network
    """Download `url` to `dest` atomically (tests inject a fake downloader instead)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response, tmp.open("wb") as out:
        while block := response.read(1 << 20):
            out.write(block)
    tmp.replace(dest)


def _jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _write(dataset: Dataset, result: BuildResult, questions: Iterable[Question]) -> None:
    dataset.dir.mkdir(parents=True, exist_ok=True)
    for path in (dataset.db, dataset.questions_path):
        path.unlink(missing_ok=True)
    with TreeStore(dataset.db) as store:
        result.write(store)
        FTS5Retriever(store)
    with dataset.questions_path.open("w", encoding="utf-8") as f:
        for q in questions:
            f.write(q.model_dump_json() + "\n")


# --- WixQA ---

_TYPE_DIRS = {"article": "articles", "feature_request": "feature-requests", "known_issue": "known-issues"}


def _product(title: str) -> str:
    head, sep, _ = title.partition(":")
    if not sep or len(head) > 40:
        return "Other"
    return head.removesuffix(" Request").strip() or "Other"


def wixqa_docs(kb_rows: Iterable[dict[str, Any]]) -> tuple[list[DocSource], dict[str, str]]:
    """Turn WixQA knowledge-base rows into documents under `type/product/slug`; return docs and id → url.

    The help center has flat URLs, so the inter-document hierarchy is article type, then the product named
    in the title prefix ("Wix Stores: …", "Wix Stores Request: …" → "Wix Stores").

    Example:
        >>> row = {"id": "a1", "url": "https://x/en/article/pay", "title": "Wix Payments: Setup",
        ...        "html_content": "<h2>Steps</h2><div>Go.</div>", "article_type": "article"}
        >>> docs, urls = wixqa_docs([row])
        >>> docs[0].parts, docs[0].text
        (('articles', 'Wix Payments', 'pay'), '# Wix Payments: Setup\\n\\n## Steps\\n\\nGo.\\n')
    """
    docs: list[DocSource] = []
    urls: dict[str, str] = {}
    seen: set[tuple[str, ...]] = set()
    for row in sorted(kb_rows, key=lambda r: (r["url"], r["id"])):
        slug = row["url"].rstrip("/").rsplit("/", 1)[-1] or row["id"][:12]
        parts = (_TYPE_DIRS.get(row.get("article_type") or "", "other"), _product(row["title"]), slug)
        if parts in seen:
            parts = (*parts[:2], f"{slug}-{row['id'][:8]}")
        seen.add(parts)
        body = html_to_markdown(row.get("html_content") or "", heading_shift=0) or (row.get("contents") or "")
        text = f"# {row['title'].strip()}\n\n{body.strip()}\n"
        docs.append(DocSource(parts=parts, url=row["url"], text=text))
        urls[row["id"]] = row["url"]
    return docs, urls


def _doc_ids_by_url(nodes: Iterable[Node]) -> dict[str, int]:
    return {n.url: n.id for n in nodes if n.kind == "doc" and n.url}


def build_wixqa(dataset: Dataset, split: str = "wixqa_expertwritten") -> tuple[BuildResult, list[Question]]:
    """Build the WixQA tree and questions from the raw files of `fetch_wixqa`."""
    docs, urls = wixqa_docs(_jsonl(dataset.raw / "wix_kb_corpus.jsonl"))
    result = assemble(
        docs, corpus_id="wixqa", site_title="support.wix.com/", site_url="https://support.wix.com/"
    )
    by_url = _doc_ids_by_url(result.nodes)
    questions = []
    for i, row in enumerate(_jsonl(dataset.raw / f"{split}.jsonl")):
        ids = row["article_ids"]
        ids = ast.literal_eval(ids) if isinstance(ids, str) else ids
        gold = [by_url[urls[a]] for a in ids if a in urls and urls[a] in by_url]
        questions.append(
            Question(id=f"{split}-{i:04d}", question=row["question"], answer=row["answer"], gold_docs=gold)
        )
    return result, questions


def fetch_wixqa(dataset: Dataset, download: Downloader = http_download) -> None:
    """Download WixQA (MIT) and build `corpus.db` + `questions.jsonl` for the expert-written split."""
    for rel in ("wix_kb_corpus/wix_kb_corpus.jsonl", "wixqa_expertwritten/test.jsonl"):
        name = "wix_kb_corpus.jsonl" if rel.startswith("wix_kb") else "wixqa_expertwritten.jsonl"
        if not (dataset.raw / name).exists():
            download(f"{WIXQA_BASE}/{rel}", dataset.raw / name)
    _write(dataset, *build_wixqa(dataset))


# --- QASPER ---


def qasper_markdown(paper: dict[str, Any]) -> str:
    """Render a QASPER paper as Markdown: title, abstract, then sections nested by their `A ::: B` names.

    Example:
        >>> print(qasper_markdown({"title": "T", "abstract": "Abs.", "full_text": [
        ...     {"section_name": "Data ::: Corpus", "paragraphs": ["We built it."]}]}))
        # T
        <BLANKLINE>
        Abs.
        <BLANKLINE>
        ## Data
        <BLANKLINE>
        ### Corpus
        <BLANKLINE>
        We built it.
        <BLANKLINE>
    """
    out = [f"# {paper['title'].strip()}", paper.get("abstract", "").strip()]
    open_path: list[str] = []
    for section in paper.get("full_text", []):
        path = [p.strip() for p in (section.get("section_name") or "Untitled").split(":::")]
        common = 0
        while common < min(len(path), len(open_path)) and path[common] == open_path[common]:
            common += 1
        if common == len(path):
            common -= 1
        for depth in range(common, len(path)):
            out.append(f"{'#' * min(depth + 2, 6)} {path[depth] or 'Untitled'}")
        open_path = path
        out.extend(p.strip() for p in section.get("paragraphs", []) if p and p.strip())
    return "\n\n".join(x for x in out if x) + "\n"


def _answer_text(answer: dict[str, Any]) -> str:
    if answer.get("unanswerable"):
        return "Unanswerable"
    if answer.get("yes_no") is not None:
        return "Yes" if answer["yes_no"] else "No"
    if answer.get("free_form_answer"):
        return str(answer["free_form_answer"])
    return "; ".join(answer.get("extractive_spans") or [])


def qasper_questions(
    papers: dict[str, dict[str, Any]], doc_ids: dict[str, int], texts: dict[int, str]
) -> list[Question]:
    """Questions with evidence, gold doc = the paper, gold spans = evidence paragraphs found in its text.

    Figure/table evidence ("FLOAT SELECTED…") is skipped; questions without any evidence are dropped.
    """
    questions = []
    for pid in sorted(papers):
        paper = papers[pid]
        doc = doc_ids[pid]
        text = texts[doc]
        for qa in paper.get("qas", []):
            evidence = [e for a in qa["answers"] for e in a["answer"].get("evidence", [])]
            if not evidence:
                continue
            spans = []
            for paragraph in dict.fromkeys(e.strip() for e in evidence if not e.startswith("FLOAT SELECTED")):
                at = text.find(paragraph) if paragraph else -1
                if at >= 0:
                    spans.append(GoldSpan(doc=doc, start=at, end=at + len(paragraph)))
            questions.append(
                Question(
                    id=f"qasper-{qa['question_id']}",
                    question=qa["question"].strip(),
                    answer=_answer_text(qa["answers"][0]["answer"]),
                    gold_docs=[doc],
                    gold_spans=spans,
                    context=paper["title"].strip(),
                )
            )
    return questions


def build_qasper(dataset: Dataset) -> tuple[BuildResult, list[Question]]:
    """Build the QASPER test-split tree (one doc per paper) and its questions from the raw archive."""
    with tarfile.open(dataset.raw / "qasper-test.tgz") as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith("qasper-test-v0.3.json"))
        extracted = tar.extractfile(member)
        assert extracted is not None
        papers: dict[str, dict[str, Any]] = json.load(extracted)
    docs = [
        DocSource(parts=(pid,), url=f"https://arxiv.org/abs/{pid}", text=qasper_markdown(papers[pid]))
        for pid in sorted(papers)
    ]
    result = assemble(docs, corpus_id="qasper", site_title="qasper/")
    by_url = _doc_ids_by_url(result.nodes)
    doc_ids = {pid: by_url[f"https://arxiv.org/abs/{pid}"] for pid in papers}
    return result, qasper_questions(papers, doc_ids, result.texts)


def fetch_qasper(dataset: Dataset, download: Downloader = http_download) -> None:
    """Download the QASPER test split (CC BY 4.0) and build `corpus.db` + `questions.jsonl`."""
    if not (dataset.raw / "qasper-test.tgz").exists():
        download(QASPER_TEST, dataset.raw / "qasper-test.tgz")
    _write(dataset, *build_qasper(dataset))


FETCHERS: dict[str, Callable[[Dataset, Downloader], None]] = {"wixqa": fetch_wixqa, "qasper": fetch_qasper}

_ID = re.compile(r"\[n(\d+)\]")


def shown_node_ids(text: str) -> set[int]:
    """Node ids that appear as `[n123]` in a rendered view.

    Example:
        >>> sorted(shown_node_ids("Auth [n29] ●\\n  Tokens [n30]"))
        [29, 30]
    """
    return {int(m) for m in _ID.findall(text)}
