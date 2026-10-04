#!/usr/bin/env bash
# Regression suite for bloat_check.py. Asserts detection AND absence of false
# positives. Run: bash tests/test_bloat_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
BC="$ROOT/scripts/bloat_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src tests docs
printf 'def add(a, b):\n    return a + b\n' > src/core.py
printf 'from src.core import add\ndef test_add():\n    assert add(1,2)==3\n' > tests/test_core.py
git add -A; git commit -qm init

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [--only X]
  local exp="$1" label="$2"; shift 2
  python3 "$BC" "$@" >$OUT/bc.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-50s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-50s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' $OUT/bc.out; fi
}
has() { grep -q "$1" $OUT/bc.out && { PASS=$((PASS+1)); printf '  ok   %-50s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-50s\n' "NOT reported: $1"; }; }
nothas() { grep -q "$1" $OUT/bc.out && { FAIL=$((FAIL+1)); printf '  FAIL %-50s\n' "false positive: $1"; } \
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
printf "STATUSES = ['TODO', \"DONE\"]\nlabel = 'FIXME' if bad else 'ok'\n" >> src/core.py
printf "export const col = { status: 'TODO' };\nconst t = \`TODO\`;\n" > src/board.ts
expect 0 "TODO inside a string literal is data, not a note" --only bare-todo
rm src/board.ts; git checkout -q -- src/core.py
printf "if s == 'TODO':  # TODO: don't hardcode\n    pass\n" >> src/core.py
expect 1 "bare TODO comment after a string literal still detected" --only bare-todo
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

# --- commented-out code: keyword followed directly by code, not by more space ---
git add -A >/dev/null 2>&1; git commit -qm wip3 >/dev/null 2>&1
printf '// const total = sum(items);\n// await save(total);\nexport const n = 1;\n' > src/cc1.ts
expect 1 "commented-out const/await detected" --only commented-code
rm src/cc1.ts
printf '# x = f(y)\n# y = g(x)\nz = 1\n' > src/cc2.py
expect 1 "commented-out python assignment detected" --only commented-code
rm src/cc2.py
printf '// foo(bar);\n// obj.baz(qux);\nexport const n = 1;\n' > src/cc3.js
expect 1 "commented-out call statements detected" --only commented-code
rm src/cc3.js
printf '// Retries are capped because the upstream rate-limits us.\n// See the runbook entry on throttling (#88) for escalation.\nexport const n = 1;\n' > src/cc4.ts
expect 0 "prose comments are not commented-out code" --only commented-code
printf '# Uses the cached value: recomputing costs a network call.\n# Callers must hold the lock (see #91).\nz = 1\n' > src/cc5.py
expect 0 "python prose comments are not commented-out code" --only commented-code
rm src/cc4.ts src/cc5.py

# --- assertionless: an assertion that is only in a comment does not count ---
printf "it('saves', () => {\n  save(1);\n  // expect(saved()).toBe(true);\n});\n" > tests/cm.test.js
printf "it('also saves', () => {\n  save(1);\n  /* expect(saved()).toBe(true); */\n});\n" > tests/cm2.test.js
printf 'def test_saves():\n    # assert saved()\n    save(1)\n' > tests/test_cm.py
expect 1 "commented-out assertions do not count" --only assertionless
has '`saves`'; has '`also saves`'; has '`test_saves`'
rm tests/cm.test.js tests/cm2.test.js tests/test_cm.py
printf "it('fetches', () => {\n  expect(get('http://x.test/a')).toBe(1); // real assertion\n});\nit('apostrophe', () => {\n  render('don\\\\'t');\n  expect(1).toBe(1);\n});\n" > tests/ok2.test.js
printf 'def test_hash():\n    assert tag("#x") == "#x"  # the hash is in a string\n' > tests/test_ok2.py
expect 0 "real assertions beside comments and URLs are not flagged" --only assertionless
rm tests/ok2.test.js tests/test_ok2.py

# --- file-creation-ratio: an edited spec must not dilute the ratio ---
mkdir -p src/components
printf 'export const Card = () => null;\n' > src/components/Card.tsx
printf "it('card', () => { expect(1).toBe(1); });\n" > tests/card.spec.ts
git add -A >/dev/null 2>&1; git commit -qm wip4 >/dev/null 2>&1
for f in a b c; do printf 'export const %s = 1;\n' "$f" > "src/new_$f.ts"; done
printf 'export const Card = () => 1;\n' > src/components/Card.tsx
printf "it('card', () => { expect(2).toBe(2); });\n" > tests/card.spec.ts
expect 1 "3 new files vs 1 edited component + 1 edited spec fires" --only file-creation-ratio --strict
has "3 new code files vs 1 edited"
printf 'def mul(a,b):\n    return a*b\n' >> src/core.py
expect 0 "3 new files vs 2 edited code files does not fire" --only file-creation-ratio --strict
rm -f src/new_a.ts src/new_b.ts src/new_c.ts
git checkout -q -- src/core.py src/components/Card.tsx tests/card.spec.ts

echo
echo "bloat_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
