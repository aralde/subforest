# Agent runs — wixqa

50 questions answered in both arms by `haiku` through `claude -p`, same retriever (BM25), call budget and view budget. No LLM judge.

- **Saw gold-doc text**: chunks: a gold-doc chunk was shown by search or a gold node was read; subforest: a gold node was read (outline lines alone do not count).
- **Gold doc shown**: the gold doc's id appeared in any tool output.

| Metric | chunks | subforest |
|---|---|---|
| Saw gold-doc text | 84.0% | 72.0% |
| Gold doc shown by any call | 84.0% | 80.0% |
| Answer token F1 vs reference | 0.387 | 0.397 |
| Tool calls (mean) | 2.2 | 3.9 |
| Input tokens (mean) | 9,568 | 15,212 |
| Seconds (median) | 10.3 | 11.3 |

Paired differences (subforest - chunks), 95% bootstrap CI:

| Metric | Δ | 95% CI | subforest only / chunks only | sign test p |
|---|---|---|---|---|
| Saw gold-doc text | -12.0% | -24.0% to +0.0% | 2 / 8 | 0.109 |
| Gold doc shown | -4.0% | -14.0% to +6.0% | 2 / 4 | 0.688 |
| Answer token F1 | +0.010 | -0.022 to +0.039 | | |
