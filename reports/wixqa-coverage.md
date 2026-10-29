# Evidence coverage — wixqa

200 questions (0 with located evidence spans), BM25 top-50 hits, query mode `raw`.

- **Gold doc**: the first view shows a chunk of (chunks) or a line for (subforest) a gold document.
- **Evidence**: chunks: a shown chunk overlaps a gold evidence span; subforest: a shown node contains the evidence and fits one `read` (≤ 800 tokens).

| Budget (tokens) | Gold doc: chunks | Gold doc: subforest | Evidence: chunks | Evidence: subforest | Tokens used: chunks / subforest |
|---|---|---|---|---|---|
| 250 | 28.0% | 57.5% | n/a | n/a | 176 / 229 |
| 500 | 42.5% | 70.5% | n/a | n/a | 426 / 480 |
| 1000 | 60.5% | 76.5% | n/a | n/a | 925 / 980 |
| 2000 | 68.0% | 82.0% | n/a | n/a | 1927 / 1845 |
