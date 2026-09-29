#!/usr/bin/env bash
# The safety boundary, executable. Threat model: the user runs
# `claude --dangerously-skip-permissions`, so nothing prompts and the only
# protection is what the code refuses to do.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-56s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "$1"; [ -s /tmp/sf.out ] && sed 's/^/       /' /tmp/sf.out | head -4; }
tree_hash() { find "$1" -type f -not -path '*/.git/*' -exec shasum {} \; 2>/dev/null | sort | shasum | cut -d' ' -f1; }

C="$TMP/repo"; mkdir -p "$C"; cd "$C"
git init -q; git config user.email e@e; git config user.name e
echo x > f.txt; git add -A; git commit -qm init

# ---------- the boundary itself ----------
python3 "$ROOT/scripts/safety_audit.py" >/tmp/sf.out 2>&1 \
  && ok "safety_audit: no destructive primitive in the plugin" \
  || bad "safety_audit: a destructive primitive is present"
grep -q "showing no guard at all            : 0" /tmp/sf.out \
  && ok "safety_audit: every writer is guarded" || bad "an unguarded writer exists"

# planting one must fail the audit
cp "$ROOT/scripts/ledger.py" "$TMP/ledger.bak"
printf '\nimport shutil\ndef _bad(p):\n    shutil.rmtree(p)\n' >> "$ROOT/scripts/ledger.py"
python3 "$ROOT/scripts/safety_audit.py" >/tmp/sf.out 2>&1 \
  && bad "audit did NOT catch a planted rmtree" || ok "audit catches a planted rmtree"
cp "$TMP/ledger.bak" "$ROOT/scripts/ledger.py"
python3 "$ROOT/scripts/safety_audit.py" >/dev/null 2>&1 \
  && ok "audit clean again after restore" || bad "restore failed"

# ---------- path traversal ----------
for name in "../../etc/passwd" "../escape" "/absolute" ".hidden"; do
  before=$(tree_hash "$C")
  python3 "$ROOT/scripts/plan_feature.py" new "$name" --kind crud >/tmp/sf.out 2>&1
  after=$(tree_hash "$C")
  if [ "$before" = "$after" ]; then ok "traversal refused, nothing written: $name"
  else bad "traversal WROTE something: $name"; fi
done

# ---------- non-git directory ----------
mkdir -p "$TMP/nogit"; cd "$TMP/nogit"
python3 "$ROOT/scripts/decide.py" new "x" >/tmp/sf.out 2>&1
grep -q "not inside a git repository" /tmp/sf.out \
  && ok "refuses to write outside a git repo" || bad "wrote outside a git repo"
[ ! -d "$TMP/nogit/decisions" ] && ok "no records created outside a repo" || bad "created records outside a repo"
cd "$C"

# ---------- --dry-run writes nothing ----------
for tool in "plan_feature.py new dr --kind crud" "prd.py new dr --kind auth" "decide.py new dr"; do
  before=$(tree_hash "$C")
  python3 "$ROOT/scripts/$tool" --dry-run >/tmp/sf.out 2>&1
  after=$(tree_hash "$C")
  [ "$before" = "$after" ] && ok "--dry-run wrote nothing: ${tool%% *}" \
    || bad "--dry-run MUTATED the tree: ${tool%% *}"
done

# ---------- shard needs --yes ----------
mkdir -p decisions
for i in $(seq 1 45); do
  printf '# ADR-%04d: d\n\n```json meta\n{"id":"ADR-%04d","title":"d","status":"accepted","date":"2026-01-15","affects":["src/**"],"options":[{"name":"a","chosen":true,"why":"x"},{"name":"b","why_not":"y"}],"assumptions":[{"id":"A1","claim":"c","verify":"true","revisit_when":"w"}]}\n```\n' $i $i > "decisions/ADR-$(printf '%04d' $i)-d.md"
done
git add -A >/dev/null 2>&1; git commit -qm bulk >/dev/null 2>&1
before=$(tree_hash "$C")
python3 "$ROOT/scripts/ledger.py" shard >/tmp/sf.out 2>&1
[ "$(tree_hash "$C")" = "$before" ] && ok "shard without --yes moved nothing" \
  || bad "shard MOVED FILES without consent"
grep -q "Nothing has changed" /tmp/sf.out && ok "shard says nothing changed" || bad "shard plan unclear"
python3 "$ROOT/scripts/ledger.py" shard --yes >/dev/null 2>&1
[ -d "$C/decisions/2026" ] && ok "shard --yes performs the move" || bad "shard --yes did not move"
[ "$(find "$C/decisions" -name 'ADR-*.md' | wc -l | tr -d ' ')" -eq 45 ] \
  && ok "shard preserved all 45 records" || bad "shard lost records"

# ---------- fix-stubs needs --yes ----------
mkdir -p "$C/research"
{ echo "# Doc"; echo; echo "Intro."; for i in 1 2 3 4 5; do echo; echo "## Section $i"; for j in $(seq 1 32); do echo "line $j"; done; done; } > "$C/research/long.md"
before=$(tree_hash "$C")
python3 "$ROOT/scripts/check_index.py" research/ --fix-stubs >/tmp/sf.out 2>&1
[ "$(tree_hash "$C")" = "$before" ] && ok "--fix-stubs without --yes rewrote nothing" \
  || bad "--fix-stubs REWROTE a file without consent"
python3 "$ROOT/scripts/check_index.py" research/ --fix-stubs --yes >/dev/null 2>&1
grep -q "^## Contents" "$C/research/long.md" && ok "--fix-stubs --yes inserts the table" \
  || bad "--fix-stubs --yes did nothing"

# ---------- the hook fails open and respects opt-in ----------
cd "$C"
echo '{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}' \
  | python3 "$ROOT/hooks/require_verification.py" >/tmp/sf.out 2>&1
grep -q '^{}$' /tmp/sf.out && ok "hook is inert with no policy file" \
  || bad "hook acted without a policy file"
echo 'not json at all' | python3 "$ROOT/hooks/require_verification.py" >/tmp/sf.out 2>&1
[ $? -eq 0 ] && ok "hook fails open on malformed input" || bad "hook crashed on bad input"

# ---------- no secret or home path leaks into a record ----------
mkdir -p .claude
python3 "$ROOT/scripts/verified.py" --name t -- python3 -c "print(1)" >/dev/null 2>&1
if [ -f .claude/verification-receipt.json ]; then
  grep -qE "$HOME|/Users/|ghp_|gho_|AKIA" .claude/verification-receipt.json \
    && bad "receipt leaks a home path or credential" || ok "receipt contains no home path or secret"
else bad "receipt not written"; fi

echo
echo "safety: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
