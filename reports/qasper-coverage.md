# Evidence coverage — qasper

1352 questions (1309 with located evidence spans), BM25 top-50 hits, query mode `raw`.

- **Gold doc**: the first view shows a chunk of (chunks) or a line for (subforest) a gold document.
- **Evidence**: chunks: a shown chunk overlaps a gold evidence span; subforest: a shown node contains the evidence and fits one `read` (≤ 800 tokens).

| Budget (tokens) | Gold doc: chunks | Gold doc: subforest | Evidence: chunks | Evidence: subforest | Tokens used: chunks / subforest |
|---|---|---|---|---|---|
| 250 | 22.0% | 44.6% | 5.7% | 8.1% | 152 / 230 |
| 500 | 33.8% | 51.5% | 11.5% | 10.2% | 398 / 482 |
| 1000 | 40.5% | 56.7% | 19.5% | 18.0% | 897 / 971 |
| 2000 | 46.6% | 60.2% | 26.2% | 31.5% | 1897 / 1476 |
