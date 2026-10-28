import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

from subforest import TreeStore
from subforest.cli import main
from subforest.eval import Dataset, bench, coverage
from subforest.eval.datasets import fetch_qasper, fetch_wixqa, qasper_markdown, wixqa_docs
from subforest.eval.html import html_to_markdown

KB = [
    {
        "id": "a1",
        "url": "https://support.example/en/article/payments-verification",
        "title": "Wix Payments: Verification Process",
        "html_content": "<div>We verify your identity.</div><h2>Checklist</h2>"
        + "<div>Upload an ID and a bank statement.</div><h2>Timing</h2>"
        + "<div>Verification takes up to 3 business days.</div>",
        "contents": "",
        "article_type": "article",
    },
    {
        "id": "a2",
        "url": "https://support.example/en/article/connect-domain",
        "title": "Connecting a Domain",
        "html_content": "<div>Point your domain to us.</div><h2>DNS records</h2><div>Add the A record.</div>",
        "contents": "",
        "article_type": "article",
    },
    {
        "id": "a3",
        "url": "https://support.example/en/article/request-dark-mode",
        "title": "Wix Editor Request: Dark mode",
        "html_content": "<div>Not available yet.</div>",
        "contents": "",
        "article_type": "feature_request",
    },
]
WIX_QUESTIONS = [
    {
        "question": "How long does payments verification take?",
        "answer": "Up to 3 days.",
        "article_ids": "['a1']",
    },
    {"question": "Which DNS record do I add for my domain?", "answer": "An A record.", "article_ids": ["a2"]},
]
PAPERS = {
    "2001.00001": {
        "title": "Parsing Learner English",
        "abstract": "We parse learner text.",
        "full_text": [
            {"section_name": "Introduction", "paragraphs": ["Learners make errors."]},
            {
                "section_name": "Data ::: Corpus",
                "paragraphs": ["The corpus has 5,124 sentences from essays."],
            },
            {
                "section_name": "Data ::: Annotation",
                "paragraphs": ["Two annotators labelled every sentence."],
            },
        ],
        "qas": [
            {
                "question": "How big is the corpus?",
                "question_id": "q1",
                "answers": [
                    {
                        "answer": {
                            "unanswerable": False,
                            "yes_no": None,
                            "free_form_answer": "",
                            "extractive_spans": ["5,124 sentences"],
                            "evidence": [
                                "The corpus has 5,124 sentences from essays.",
                                "FLOAT SELECTED: Table 1",
                            ],
                        }
                    }
                ],
            },
            {
                "question": "Unanswerable one?",
                "question_id": "q2",
                "answers": [{"answer": {"unanswerable": True, "evidence": []}}],
            },
        ],
    }
}


def fake_downloader(sources: dict[str, bytes]):  # type: ignore[no-untyped-def]
    def download(url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(next(v for k, v in sources.items() if url.endswith(k)))

    return download


def jsonl(rows: list[dict[str, object]]) -> bytes:
    return "".join(json.dumps(r) + "\n" for r in rows).encode()


def qasper_tgz() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = json.dumps(PAPERS).encode()
        info = tarfile.TarInfo("qasper-test-v0.3.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def wixqa(tmp_path: Path) -> Dataset:
    dataset = Dataset("wixqa", tmp_path)
    fetch_wixqa(
        dataset,
        fake_downloader(
            {"wix_kb_corpus.jsonl": jsonl(KB), "wixqa_expertwritten/test.jsonl": jsonl(WIX_QUESTIONS)}
        ),
    )
    return dataset


@pytest.fixture
def qasper(tmp_path: Path) -> Dataset:
    dataset = Dataset("qasper", tmp_path)
    fetch_qasper(dataset, fake_downloader({".tgz": qasper_tgz()}))
    return dataset


def test_html_to_markdown_keeps_structure() -> None:
    html = (
        "<div><h2>A</h2><p>One&nbsp;two</p><script>x()</script><ul><li>i</li><li>j</li></ul>"
        + "<h4>B</h4>x<br/>y</div>"
    )
    assert html_to_markdown(html) == "## A\n\nOne two\n\n- i\n\n- j\n\n#### B\n\nx\ny"
    assert html_to_markdown("<h2>A</h2>", heading_shift=1) == "### A"


def test_wixqa_hierarchy_by_type_and_product() -> None:
    docs, urls = wixqa_docs(KB)
    assert [d.parts for d in docs] == [
        ("articles", "Other", "connect-domain"),
        ("articles", "Wix Payments", "payments-verification"),
        ("feature-requests", "Wix Editor", "request-dark-mode"),
    ]
    assert urls["a1"].endswith("payments-verification")


def test_wixqa_fetch_maps_gold_docs(wixqa: Dataset) -> None:
    questions = wixqa.questions()
    with TreeStore(wixqa.db) as store:
        assert [store.get_node(q.gold_docs[0]).title for q in questions] == [
            "Wix Payments: Verification Process",
            "Connecting a Domain",
        ]
        assert "## Timing" in (store.doc_text(questions[0].gold_docs[0]) or "")


def test_qasper_markdown_nests_sections() -> None:
    md = qasper_markdown(PAPERS["2001.00001"])
    assert "## Data\n\n### Corpus\n\nThe corpus" in md and "### Annotation" in md
    assert md.count("## Data") == 1


def test_qasper_fetch_locates_evidence(qasper: Dataset) -> None:
    (q,) = qasper.questions()
    assert q.answer == "5,124 sentences" and q.context == "Parsing Learner English"
    with TreeStore(qasper.db) as store:
        text = store.doc_text(q.gold_docs[0]) or ""
    (span,) = q.gold_spans
    assert text[span.start : span.end] == "The corpus has 5,124 sentences from essays."


def test_bench_reports_determinism(wixqa: Dataset) -> None:
    report = bench(wixqa, queries=2)
    assert report.deterministic and report.docs == 3 and report.queries == 2
    assert set(report.latency_ms) == {"search", "induce", "render"}
    assert "| yes |" in report.markdown()


def test_coverage_counts_docs_and_evidence(wixqa: Dataset, qasper: Dataset) -> None:
    wix = coverage(wixqa, budgets=[40, 400])
    assert wix.rate("subforest", 400, "doc") == 1.0 and wix.rate("chunks", 400, "doc") == 1.0
    assert wix.with_spans == 0 and "n/a | n/a" in wix.markdown()
    qas = coverage(qasper, budgets=[400], mode="titled")
    assert qas.rate("chunks", 400, "evidence") == 1.0
    assert qas.rate("subforest", 400, "evidence") == 1.0


def test_cli_offline_commands(wixqa: Dataset, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "reports"
    assert main(["bench", "wixqa", "--root", str(wixqa.root), "--queries", "1", "--out", str(out)]) == 0
    assert main(["coverage", "wixqa", "--root", str(wixqa.root), "--budgets", "100", "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["wixqa-bench.md", "wixqa-coverage.md"]
    shutil.rmtree(wixqa.dir)
    assert main(["bench", "wixqa", "--root", str(wixqa.root)]) == 2
