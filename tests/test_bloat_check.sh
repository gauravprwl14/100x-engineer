#!/usr/bin/env bash
# Regression suite for bloat_check.py. Asserts detection AND absence of false
# positives. Run: bash tests/test_bloat_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
BC="$ROOT/scripts/bloat_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src tests docs
printf 'def add(a, b):\n    return a + b\n' > src/core.py
printf 'from src.core import add\ndef test_add():\n    assert add(1,2)==3\n' > tests/test_core.py
git add -A; git commit -qm init

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [--only X]
  local exp="$1" label="$2"; shift 2
  python3 "$BC" "$@" >/tmp/bc.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-50s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-50s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' /tmp/bc.out; fi
}
has() { grep -q "$1" /tmp/bc.out && { PASS=$((PASS+1)); printf '  ok   %-50s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-50s\n' "NOT reported: $1"; }; }
nothas() { grep -q "$1" /tmp/bc.out && { FAIL=$((FAIL+1)); printf '  FAIL %-50s\n' "false positive: $1"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-50s\n' "no false positive: $1"; }; }

# --- clean change: must pass ---
printf 'def add(a,b):\n    return a+b\n\ndef sub(a,b):\n    return a-b\n' > src/core.py
printf '\ndef test_sub():\n    from src.core import sub\n    assert sub(3,1)==2\n' >> tests/test_core.py
expect 0 "clean diff produces no findings"

# --- assertionless, three languages ---
printf 'from src.core import add\ndef test_runs():\n    add(1,2)\n' > tests/test_bad.py
printf "describe('t',()=>{\n it('empty',()=>{ go(); });\n it('real',()=>{ expect(go()).toBe(1); });\n});\n" > tests/t.test.js
printf 'package s\n\nfunc TestGood(t *testing.T){\n if Add(1,2)!=3 { t.Fatal("x") }\n}\n\nfunc TestBad(t *testing.T){\n Add(1,2)\n}\n' > tests/s_test.go
expect 1 "assertionless tests detected" --only assertionless
has "test_runs"; has "empty"; has "TestBad"
nothas "'real'"; nothas "TestGood"

# --- commented-out code ---
rm tests/test_bad.py tests/t.test.js tests/s_test.go
printf 'def mul(a,b):\n    # if a==0:\n    #     return 0\n    return a*b\n' >> src/core.py
expect 1 "commented-out code detected" --only commented-code

# --- bare TODO vs referenced TODO ---
git add -A; git commit -qm wip
printf '# TODO: clean up\n' >> src/core.py
expect 1 "bare TODO detected" --only bare-todo
git checkout -q -- src/core.py
printf '# TODO(#412): clean up\n' >> src/core.py
expect 0 "TODO with issue ref is allowed" --only bare-todo
git checkout -q -- src/core.py

# --- unrequested docs vs allowed locations ---
printf '# Notes\n' > RANDOM_NOTES.md
expect 1 "new doc outside docs/ detected" --only new-docs
rm RANDOM_NOTES.md
printf '# Notes\n' > docs/notes.md
expect 0 "new doc inside docs/ is allowed" --only new-docs
rm docs/notes.md
printf '# Readme\n' > README.md
expect 0 "README.md is allowed" --only new-docs
rm README.md

# --- focused / silently-skipped tests ---
git add -A >/dev/null 2>&1; git commit -qm wip2 >/dev/null 2>&1
printf "describe.only('x',()=>{ it('a',()=>{ expect(1).toBe(1); }); });\n" > tests/focus.test.js
expect 1 "focused test detected" --only focused-tests
printf 'import pytest\n@pytest.mark.skip\ndef test_s():\n    assert True\n' > tests/test_sk.py
expect 1 "skipped test without reason detected" --only focused-tests
rm -f tests/focus.test.js tests/test_sk.py
printf "describe('x',()=>{ it('a',()=>{ expect(1).toBe(1); }); });\n" > tests/ok.test.js
expect 0 "ordinary test is not flagged" --only focused-tests
rm -f tests/ok.test.js

echo
echo "bloat_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
