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
echo "=== seeded-defect evals ==="
python3 scripts/run_evals.py | tail -14 || rc=1
echo
echo "=== skill contract lint ==="
python3 scripts/lint_skills.py || rc=1
echo
[ "$rc" -eq 0 ] && echo "ALL SUITES PASSED" || echo "FAILURES PRESENT"
exit "$rc"
