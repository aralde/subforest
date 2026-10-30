# Agent runs — wixqa

200 questions (raw mode) answered in both arms by `haiku` through `claude -p`, same retriever (BM25), call budget and view budget.

- **Saw gold-doc text**: chunks: a gold-doc chunk was shown by search or a gold node was read; subforest: a gold node was read (outline lines alone do not count).
- **Gold doc shown**: the gold doc's id appeared in any tool output.
- **Judged correct**: verdict of `sonnet` via `claude -p`, blind to the arm, against the reference answer (200 questions judged in both arms).

| Metric | chunks | subforest |
|---|---|---|
| Saw gold-doc text | 79.0% | 76.0% |
| Gold doc shown | 79.0% | 82.0% |
| Judged correct | 58.0% | 58.5% |
| Judged correct or partial | 88.0% | 90.0% |
| Answer token F1 vs reference | 0.374 | 0.381 |
| Tool calls (mean) | 2.4 | 4.3 |
| Input tokens (mean) | 10,341 | 17,993 |
| Seconds (median) | 10.6 | 11.8 |

Paired differences (subforest - chunks), 95% bootstrap CI:

| Metric | Δ | 95% CI | subforest only / chunks only | sign test p |
|---|---|---|---|---|
| Saw gold-doc text | -3.0% | -9.0% to +3.0% | 15 / 21 | 0.405 |
| Gold doc shown | +3.0% | -2.5% to +8.5% | 18 / 12 | 0.362 |
| Judged correct | +0.5% | -6.0% to +7.5% | 26 / 25 | 1.000 |
| Judged correct or partial | +2.0% | -2.5% to +7.0% | 14 / 10 | 0.541 |
| Answer token F1 | +0.007 | -0.005 to +0.019 | | |
