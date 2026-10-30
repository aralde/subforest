# Agent runs — wixqa

50 questions (raw mode) answered in both arms by `haiku` through `claude -p`, same retriever (BM25), call budget and view budget. No LLM judge.

- **Saw gold-doc text**: chunks: a gold-doc chunk was shown by search or a gold node was read; subforest: a gold node was read (outline lines alone do not count).
- **Gold doc shown**: the gold doc's id appeared in any tool output.
- **Judged correct**: verdict of `sonnet` via `claude -p`, blind to the arm, against the reference answer (50 questions judged in both arms).

| Metric | chunks | subforest |
|---|---|---|
| Saw gold-doc text | 84.0% | 72.0% |
| Gold doc shown | 84.0% | 80.0% |
| Judged correct | 72.0% | 70.0% |
| Judged correct or partial | 92.0% | 92.0% |
| Answer token F1 vs reference | 0.387 | 0.397 |
| Tool calls (mean) | 2.2 | 3.9 |
| Input tokens (mean) | 9,568 | 15,212 |
| Seconds (median) | 10.3 | 11.3 |

Paired differences (subforest - chunks), 95% bootstrap CI:

| Metric | Δ | 95% CI | subforest only / chunks only | sign test p |
|---|---|---|---|---|
| Saw gold-doc text | -12.0% | -24.0% to +0.0% | 2 / 8 | 0.109 |
| Gold doc shown | -4.0% | -14.0% to +6.0% | 2 / 4 | 0.688 |
| Judged correct | -2.0% | -14.0% to +10.0% | 4 / 5 | 1.000 |
| Judged correct or partial | +0.0% | -10.0% to +10.0% | 3 / 3 | 1.000 |
| Answer token F1 | +0.010 | -0.022 to +0.039 | | |
