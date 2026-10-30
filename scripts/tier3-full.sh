#!/usr/bin/env bash
# Tier 3 full runs on the Claude subscription: WixQA (200) and QASPER (400, titled), both arms, then the judge.
# Every step resumes from its JSONL; exit code 75 means the usage window is spent, so wait and retry.
set -u
RUNS="${SUBFOREST_RUNS:-$HOME/.cache/subforest/runs}"
WAIT="${SUBFOREST_LIMIT_WAIT:-1200}"
sf() { uv run --quiet subforest "$@"; }

steps=(
  "agent run wixqa --out $RUNS/wixqa --limit 200"
  "agent run qasper --out $RUNS/qasper --limit 400 --mode titled --evidence-only --one-per-doc"
  "agent judge wixqa --runs $RUNS/wixqa"
  "agent judge qasper --runs $RUNS/qasper"
)
for step in "${steps[@]}"; do
  while true; do
    echo "$(date -Is) start: $step"
    # shellcheck disable=SC2086
    sf $step
    code=$?
    if [ "$code" -eq 75 ]; then
      echo "$(date -Is) usage limit; sleeping ${WAIT}s"
      sleep "$WAIT"
    elif [ "$code" -ne 0 ]; then
      echo "$(date -Is) failed with $code: $step"
      exit "$code"
    else
      break
    fi
  done
done
echo "$(date -Is) all steps done"
