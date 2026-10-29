# Evidence coverage — qasper

1352 questions (1309 with located evidence spans), BM25 top-50 hits, query mode `titled`.

- **Gold doc**: the first view shows a chunk of (chunks) or a line for (subforest) a gold document.
- **Evidence**: chunks: a shown chunk overlaps a gold evidence span; subforest: a shown node contains the evidence and fits one `read` (≤ 800 tokens).

| Budget (tokens) | Gold doc: chunks | Gold doc: subforest | Evidence: chunks | Evidence: subforest | Tokens used: chunks / subforest |
|---|---|---|---|---|---|
| 250 | 73.9% | 99.5% | 1.3% | 8.6% | 127 / 231 |
| 500 | 99.5% | 99.9% | 9.5% | 12.5% | 399 / 482 |
| 1000 | 99.9% | 100.0% | 28.0% | 43.1% | 897 / 925 |
| 2000 | 100.0% | 100.0% | 46.2% | 58.9% | 1898 / 1090 |
