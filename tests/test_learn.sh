#!/usr/bin/env bash
# Regression suite for scripts/learn.py — project lessons, recall, lint and promotion.
# Asserts detection AND absence of false positives, in a throwaway consumer repo.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
L="$ROOT/scripts/learn.py"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-58s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "$1"; [ -s $OUT/l.out ] && sed 's/^/       /' $OUT/l.out | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -q -- "$1" $OUT/l.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -q -- "$1" $OUT/l.out && bad "false positive: $1" || ok "no false positive: $1"; }

C="$TMP/consumer"; mkdir -p "$C/src/auth" "$C/src/authz" "$C/tests/integration"; cd "$C"
git init -q; git config user.email e@e; git config user.name e
echo 'export const login = 1;' > src/auth/login.ts
echo 'export const policy = 1;' > src/authz/policy.ts
printf 'import pytest\n\n\ndef db():\n    pass\n' > tests/integration/conftest.py
printf '# AGENTS.md\n\n## Rules\n\n1. Run the tests.\n\n## Gotchas\n\n- Existing gotcha.\n\n## Contact\n\nnobody\n' > AGENTS.md
git add -A; git commit -qm init

# ---------- add + relevant: glob recall ----------
python3 "$L" add "Session cookies must stay SameSite=Lax because the SSO callback is a cross-site redirect" \
  --kind gotcha --affects "src/auth/**" --source "src/auth/login.ts:1" >$OUT/l.out 2>&1
rc_is 0 $? "add: exits 0"
python3 "$L" add "Integration suite needs docker compose up db first, otherwise a DNS error" \
  --kind gotcha --affects "tests/integration/*.py" --source "tests/integration/conftest.py:4" >$OUT/l.out 2>&1

python3 "$L" relevant src/auth/login.ts >$OUT/l.out 2>&1
rc_is 0 $? "relevant: exits 0"
has "LESSON-0001"
no "LESSON-0002"
python3 "$L" relevant "$C/src/auth/login.ts" >$OUT/l.out 2>&1
has "LESSON-0001"
python3 "$L" relevant ./tests/integration/test_orders.py >$OUT/l.out 2>&1
has "LESSON-0002"
python3 "$L" relevant src/authz/policy.ts >$OUT/l.out 2>&1
has "no recorded lesson affects"
no "LESSON-0001"
python3 "$L" relevant tests/integration/sub/deep.py >$OUT/l.out 2>&1
no "LESSON-0002"

# ---------- lint ----------
python3 "$L" lint >$OUT/l.out 2>&1
rc_is 0 $? "lint: attached, sourced lessons pass"
no "ERROR"

python3 "$L" add "Generated client is rebuilt by make proto; hand edits are silently reverted" \
  --kind gotcha --source "ADR-0004" >$OUT/l.out 2>&1
python3 "$L" lint >$OUT/l.out 2>&1
rc_is 1 $? "lint: rejects a lesson with no affects glob"
has "no \`affects\` glob"
python3 - "$C/docs/engineering/lessons" <<'PY'
import json, re, pathlib, sys
for p in pathlib.Path(sys.argv[1]).glob("LESSON-0003-*.md"):
    t = p.read_text(); m = re.search(r"```json meta\n(.*?)\n```", t, re.S)
    meta = json.loads(m.group(1)); meta["affects"] = ["src/gen/**"]; meta["source"] = None
    p.write_text(t[:m.start(1)] + json.dumps(meta, indent=2) + t[m.end(1):])
PY
python3 "$L" lint >$OUT/l.out 2>&1
rc_is 1 $? "lint: rejects a lesson with no source"
has "no \`source\`"
has "matches no tracked file"

python3 - "$C/docs/engineering/lessons" <<'PY'
import json, re, pathlib, sys
for p in pathlib.Path(sys.argv[1]).glob("LESSON-0003-*.md"):
    t = p.read_text(); m = re.search(r"```json meta\n(.*?)\n```", t, re.S)
    meta = json.loads(m.group(1)); meta["affects"] = ["src/auth/**"]; meta["source"] = "src/gone.ts:9"
    p.write_text(t[:m.start(1)] + json.dumps(meta, indent=2) + t[m.end(1):])
PY
python3 "$L" lint >$OUT/l.out 2>&1
rc_is 1 $? "lint: rejects a lesson whose source path no longer exists"
has "no longer exists"

python3 - "$C/docs/engineering/lessons" <<'PY'
import json, re, pathlib, sys
for p in pathlib.Path(sys.argv[1]).glob("LESSON-0003-*.md"):
    t = p.read_text(); m = re.search(r"```json meta\n(.*?)\n```", t, re.S)
    meta = json.loads(m.group(1)); meta["source"] = "ADR-0004"
    p.write_text(t[:m.start(1)] + json.dumps(meta, indent=2) + t[m.end(1):])
PY
python3 "$L" lint >$OUT/l.out 2>&1
rc_is 0 $? "lint: an ADR-id source is not treated as a missing path"

# ---------- promote: prints, writes nothing without --yes ----------
before=$(shasum AGENTS.md docs/engineering/lessons/LESSON-0001-*.md | shasum)
python3 "$L" promote LESSON-0001 >$OUT/l.out 2>&1
rc_is 0 $? "promote: without --yes exits 0"
has "target : AGENTS.md"
has "end of section '## Gotchas'"
has "(LESSON-0001)"
has "Nothing has changed"
after=$(shasum AGENTS.md docs/engineering/lessons/LESSON-0001-*.md | shasum)
[ "$before" = "$after" ] && ok "promote: without --yes wrote nothing" || bad "promote: WROTE without --yes"

python3 "$L" promote LESSON-0001 --yes >$OUT/l.out 2>&1
rc_is 0 $? "promote --yes: exits 0"
python3 - "$C/AGENTS.md" <<'PY' >$OUT/l.out 2>&1
import sys
t = open(sys.argv[1]).read()
g, c = t.index("## Gotchas"), t.index("## Contact")
snip = t.index("(LESSON-0001)")
assert g < snip < c, (g, snip, c)
assert t.index("- Existing gotcha.") < snip
print("snippet inside Gotchas")
PY
rc_is 0 $? "promote --yes: snippet lands at the end of '## Gotchas'"
grep -q '"promoted_to": "AGENTS.md#gotchas"' docs/engineering/lessons/LESSON-0001-*.md \
  && ok "promote --yes: lesson marked promoted_to" || bad "promote --yes: lesson not marked"

python3 "$L" promote LESSON-0001 --yes >$OUT/l.out 2>&1
rc_is 0 $? "promote: second run is a no-op"
has "already promoted"
[ "$(grep -c '(LESSON-0001)' AGENTS.md)" -eq 1 ] && ok "promote: snippet not duplicated" \
  || bad "promote: snippet duplicated"

python3 "$L" promote LESSON-0002 --section "## Testing" --yes >$OUT/l.out 2>&1
grep -q "^## Testing" AGENTS.md && ok "promote: missing section is appended" || bad "promote: section not created"

python3 "$L" add "Prefer small functions everywhere in this codebase" --kind preference \
  --affects "src/**" --source "ADR-0001" >$OUT/l.out 2>&1
python3 "$L" promote LESSON-0004 --yes >$OUT/l.out 2>&1
rc_is 1 $? "promote: refuses a lesson that fails lint"
has "not stable enough"
grep -q "(LESSON-0004)" AGENTS.md && bad "promote: wrote an unstable lesson" || ok "promote: unstable lesson not written"

python3 "$L" promote LESSON-9999 >$OUT/l.out 2>&1
rc_is 2 $? "promote: unknown id exits 2"

cd "$ROOT"
echo
echo "learn: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
