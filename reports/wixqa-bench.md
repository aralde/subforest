# Bench — wixqa

| Docs | Nodes | Chunks | Build (s) | DB (MB) | Deterministic |
|---|---|---|---|---|---|
| 6,221 | 32,597 | 34,604 | 7.5 | 46.5 | yes |

Latency over 200 dataset questions (ms):

| Step | p50 | p95 | max |
|---|---|---|---|
| search | 66.6 | 109.7 | 159.0 |
| induce | 5.4 | 6.1 | 6.5 |
| render | 10.1 | 19.2 | 24.1 |
