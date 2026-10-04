#!/usr/bin/env bash
# Run every suite in this plugin. This is the plugin's own prove-it command.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
rc=0
for t in tests/test_*.sh; do
  echo "=== $t ==="
  bash "$t" || rc=1
  echo
done
# Prints the last <n> lines of a command's output (all of it on failure) and
# returns the command's own exit status. A bare `cmd | tail` returns tail's
# status, which silently passed an eval regression.
tail_status() {
  local n="$1"; shift
  local out status
  out="$("$@" 2>&1)"; status=$?
  if [ "$status" -eq 0 ]; then printf '%s\n' "$out" | tail -n "$n"
  else printf '%s\n' "$out"; echo "exit status $status: $*"; fi
  return "$status"
}
if tail_status 1 python3 -c 'import sys; sys.exit(3)' >/dev/null; then
  echo "run_all.sh self-test: tail_status swallowed a non-zero exit"; rc=1
fi
echo "=== seeded-defect evals ==="
tail_status 14 python3 scripts/run_evals.py || rc=1
echo
echo "=== skill contract lint ==="
python3 scripts/lint_skills.py || rc=1

echo "=== term index freshness ==="
python3 scripts/check_index.py --check-terms >/dev/null || { echo "TERMS.md is stale: run python3 scripts/check_index.py --gen-terms"; rc=1; }
echo
[ "$rc" -eq 0 ] && echo "ALL SUITES PASSED" || echo "FAILURES PRESENT"
exit "$rc"
