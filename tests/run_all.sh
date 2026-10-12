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
# lint_skills must find this plugin's skills from any directory, and must refuse
# (exit 2) rather than pass when there is nothing to lint.
LS_TMP="$(mktemp -d)"
( cd "$LS_TMP" && python3 "$ROOT/scripts/lint_skills.py" >/dev/null 2>&1 ) \
  || { echo "lint_skills self-test: failed when run outside the plugin root"; rc=1; }
python3 scripts/lint_skills.py --root "$LS_TMP" >/dev/null 2>&1
[ $? -eq 2 ] || { echo "lint_skills self-test: no skills/ dir did not exit 2"; rc=1; }
mkdir -p "$LS_TMP/skills"
python3 scripts/lint_skills.py --root "$LS_TMP" >/dev/null 2>&1
[ $? -eq 2 ] || { echo "lint_skills self-test: empty skills/ dir did not exit 2"; rc=1; }
rm -rf "$LS_TMP"

# Sibling plugins in this marketplace (plugins/<name>/): their own suites and the same
# skill contract. They are not part of 100x's counts (root skills/ and tests/ only).
for p in plugins/*/; do
  [ -d "$p" ] || continue
  for t in "$p"tests/test_*.sh; do
    [ -f "$t" ] || continue
    echo "=== $t ==="
    bash "$t" || rc=1
    echo
  done
  if [ -d "${p}skills" ]; then
    echo "=== skill contract lint: $p ==="
    python3 scripts/lint_skills.py --root "$p" || rc=1
    echo
  fi
done

echo "=== term index freshness ==="
python3 scripts/check_index.py --check-terms >/dev/null || { echo "TERMS.md is stale: run python3 scripts/check_index.py --gen-terms"; rc=1; }
echo
[ "$rc" -eq 0 ] && echo "ALL SUITES PASSED" || echo "FAILURES PRESENT"
exit "$rc"
