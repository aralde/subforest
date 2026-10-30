# Agent runs — qasper

400 questions (titled mode) answered in both arms by `haiku` through `claude -p`, same retriever (BM25), call budget and view budget.

- **Saw gold-doc text**: chunks: a gold-doc chunk was shown by search or a gold node was read; subforest: a gold node was read (outline lines alone do not count).
- **Gold doc shown**: the gold doc's id appeared in any tool output.
- **Saw gold evidence**: the start or end of a gold evidence paragraph appeared in any tool output (400 questions with located evidence).
- **Judged correct**: verdict of `sonnet` via `claude -p`, blind to the arm, against the reference answer (400 questions judged in both arms).
- **Judge check**: 40 labelled answers: exact agreement 97.5%, correct-vs-not agreement 97.5%.

| Metric | chunks | subforest |
|---|---|---|
| Saw gold-doc text | 100.0% | 100.0% |
| Gold doc shown | 100.0% | 100.0% |
| Saw gold evidence | 80.0% | 85.8% |
| Judged correct | 57.5% | 61.3% |
| Judged correct or partial | 73.0% | 75.8% |
| Answer token F1 vs reference | 0.099 | 0.102 |
| Tool calls (mean) | 2.9 | 4.2 |
| Input tokens (mean) | 15,851 | 19,331 |
| Seconds (median) | 11.4 | 12.2 |

Paired differences (subforest - chunks), 95% bootstrap CI:

| Metric | Δ | 95% CI | subforest only / chunks only | sign test p |
|---|---|---|---|---|
| Saw gold-doc text | +0.0% | +0.0% to +0.0% | 0 / 0 | 1.000 |
| Gold doc shown | +0.0% | +0.0% to +0.0% | 0 / 0 | 1.000 |
| Saw gold evidence | +5.8% | +1.5% to +10.0% | 51 / 28 | 0.013 |
| Judged correct | +3.8% | -0.5% to +8.0% | 49 / 34 | 0.124 |
| Judged correct or partial | +2.8% | -0.8% to +6.2% | 31 / 20 | 0.161 |
| Answer token F1 | +0.002 | -0.004 to +0.009 | | |
