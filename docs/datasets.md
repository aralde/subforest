# Datasets

Checked before downloading. Data is never committed: `subforest data fetch <name>` downloads into
`$SUBFOREST_DATA` (default `~/.cache/subforest/datasets`) and builds `corpus.db` + `questions.jsonl` there.

| Dataset | Source | License | Used for | Size |
|---|---|---|---|---|
| WixQA (expert-written split + KB corpus) | [Wix/WixQA](https://huggingface.co/datasets/Wix/WixQA) | MIT | Tier 1–3 (main replication) | 200 questions, 6,221 help-center articles |
| QASPER (test split v0.3) | [allenai/qasper](https://huggingface.co/datasets/allenai/qasper), archive on `qasper-dataset.s3.us-west-2.amazonaws.com` | CC BY 4.0 | Tier 1–2 (evidence coverage) | 416 papers, 1,352 questions with evidence |
| FinanceBench | — | not checked yet | deferred: long PDFs need outline parsing (out of MVP) | — |

Checked on 2026-10-28 from the dataset cards' license fields.

## Notes

- **WixQA** help-center URLs are flat (`/en/article/<slug>`), so the inter-document tree is built as
  article type → product (title prefix, e.g. "Wix Stores: …") → article. Sections come from the article HTML
  (`<h2>`, `<h4>`). Gold = the questions' `article_ids` mapped to document nodes. No evidence spans.
- **QASPER** is one document per paper; sections come from `full_text` (`A ::: B` = nested). Gold evidence
  paragraphs are located in the rendered text (figure/table evidence skipped); 1,309 of 1,352 questions have at
  least one located span. Questions are written against a single paper, so `--mode titled` prefixes the title.
