#!/usr/bin/env bash
# Resume bench: can a fresh headless session answer seven questions about a multi-PR workstream,
# with and without the workstream brief injected at SessionStart? Spends money: needs --yes.
# --setting-sources project keeps the runner's own ~/.claude rules and memory out of both arms.
#   run.sh --yes [--runs 3] [--arms none,brief] [--model sonnet] [--max-cost-usd 0.5]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
RUNS=3; ARMS="none,brief"; MODEL="sonnet"; CAP="0.5"; YES=0
while [ $# -gt 0 ]; do case "$1" in
  --yes) YES=1;; --runs) RUNS="$2"; shift;; --arms) ARMS="$2"; shift;;
  --model) MODEL="$2"; shift;; --max-cost-usd) CAP="$2"; shift;;
  *) echo "unknown flag $1" >&2; exit 2;; esac; shift; done
n_arms=$(echo "$ARMS" | tr ',' '\n' | wc -l | tr -d ' ')
if [ "$YES" -ne 1 ]; then
  echo "This runs $((RUNS * n_arms)) claude -p sessions ($MODEL), each capped at \$$CAP. Re-run with --yes."; exit 1
fi
OUT="$HERE/results/$(date +%Y%m%dT%H%M%S)"; mkdir -p "$OUT"
for arm in ${ARMS//,/ }; do
  for i in $(seq 1 "$RUNS"); do
    ws=$(mktemp -d); bash "$HERE/scaffold.sh" "$ws"
    extra=(); [ "$arm" = brief ] && extra=(--plugin-dir "$HERE/brief-plugin")
    ( cd "$ws" && claude -p ${extra[@]+"${extra[@]}"} --model "$MODEL" --max-budget-usd "$CAP" --setting-sources project \
        --allowedTools "Bash(git:*)" Read Grep Glob \
        --output-format json --json-schema "$(cat "$HERE/schema.json")" \
        "$(cat "$HERE/prompt.md")" ) > "$OUT/$arm-$i.json" || echo "run $arm-$i exited non-zero" >&2
    rm -rf "$ws"; echo "done $arm-$i"
  done
done
python3 "$HERE/grade.py" "$OUT" | tee "$OUT/summary.md"
