# Agent runs — qasper

50 questions (titled mode) answered in both arms by `haiku` through `claude -p`, same retriever (BM25), call budget and view budget. No LLM judge.

- **Saw gold-doc text**: chunks: a gold-doc chunk was shown by search or a gold node was read; subforest: a gold node was read (outline lines alone do not count).
- **Gold doc shown**: the gold doc's id appeared in any tool output.
- **Saw gold evidence**: the start or end of a gold evidence paragraph appeared in any tool output (50 questions with located evidence).
- **Judged correct**: verdict of `sonnet` via `claude -p`, blind to the arm, against the reference answer (50 questions judged in both arms).
- **Judge check**: 40 labelled answers: exact agreement 97.5%, correct-vs-not agreement 97.5%.

| Metric | chunks | subforest |
|---|---|---|
| Saw gold-doc text | 100.0% | 100.0% |
| Gold doc shown | 100.0% | 100.0% |
| Saw gold evidence | 68.0% | 90.0% |
| Judged correct | 52.0% | 52.0% |
| Judged correct or partial | 66.0% | 68.0% |
| Answer token F1 vs reference | 0.089 | 0.089 |
| Tool calls (mean) | 2.6 | 4.1 |
| Input tokens (mean) | 13,890 | 18,507 |
| Seconds (median) | 10.7 | 11.2 |

Paired differences (subforest - chunks), 95% bootstrap CI:

| Metric | Δ | 95% CI | subforest only / chunks only | sign test p |
|---|---|---|---|---|
| Saw gold-doc text | +0.0% | +0.0% to +0.0% | 0 / 0 | 1.000 |
| Gold doc shown | +0.0% | +0.0% to +0.0% | 0 / 0 | 1.000 |
| Saw gold evidence | +22.0% | +6.0% to +36.0% | 14 / 3 | 0.013 |
| Judged correct | +0.0% | -12.0% to +12.0% | 5 / 5 | 1.000 |
| Judged correct or partial | +2.0% | -6.0% to +10.0% | 3 / 2 | 1.000 |
| Answer token F1 | +0.000 | -0.017 to +0.019 | | |
