#!/usr/bin/env bash
# agents/*.md must match the operating model's roster and load as Claude Code plugin agents.
# Both failure modes are silent at runtime (an unparseable file loads with fields ignored; a
# missing preloaded skill is skipped), so this suite is the only place they surface.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LINT="$ROOT/scripts/agents_lint.py"
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }

# Skills other branches are building at the same time; a miss on these is printed apart from
# real errors so the merge can tell "not merged yet" from "wrong name".
PENDING="ui-baseline,app-security,release-rollout,data-lifecycle,qa-strategy,orchestrate"

echo "=== the real agents ==="
python3 "$LINT" --root "$ROOT" --pending "$PENDING" >"$OUT/real.out" 2>&1; rc=$?
sed 's/^/     /' "$OUT/real.out"
if [ "$rc" -eq 0 ]; then ok "every agent passes (roster, frontmatter, tools, skills, protocol)"
elif ! grep -q '  ERROR ' "$OUT/real.out"; then
  bad "only pending-skill misses remain (expected until the parallel skills merge)"
else bad "agents have real errors"; fi

# A clean fixture: real agents and operating model, a stub SKILL.md for every preloaded skill.
mk_fixture() {
  local d="$1"; mkdir -p "$d/agents" "$d/docs" "$d/.claude-plugin"
  cp "$ROOT"/agents/*.md "$d/agents/"
  cp "$ROOT/docs/OPERATING-MODEL.md" "$d/docs/"
  cp "$ROOT/.claude-plugin/plugin.json" "$d/.claude-plugin/"
  for s in $(grep -hoE '^  - [a-z0-9-]+:[a-z0-9-]+' "$d"/agents/*.md | sed 's/.*://' | sort -u); do
    mkdir -p "$d/skills/$s"; echo "---" > "$d/skills/$s/SKILL.md"
  done
}

echo "=== no false positive on a clean fixture ==="
mk_fixture "$OUT/clean"
python3 "$LINT" --root "$OUT/clean" >"$OUT/clean.out" 2>&1 \
  && ok "clean fixture passes" || { bad "clean fixture flagged"; sed 's/^/     /' "$OUT/clean.out"; }

# expect_error <label> <grep pattern> <mutation command run inside the fixture>
expect_error() {
  local label="$1" pat="$2" d="$OUT/f$((PASS+FAIL))"; shift 2
  mk_fixture "$d"; ( cd "$d" && eval "$*" )
  python3 "$LINT" --root "$d" ${EXTRA:-} >"$d.out" 2>&1; local rc=$?
  if [ "$rc" -ne 0 ] && grep -q -- "$pat" "$d.out"; then ok "$label"
  else bad "$label (rc=$rc)"; sed 's/^/     /' "$d.out"; fi
}

echo "=== detection ==="
expect_error "reviewer with Edit is rejected" "read-only role has write tools" \
  "sed -i.bak 's/^tools: Read, Grep, Glob, Bash, Skill/tools: Read, Edit, Bash/' agents/code-reviewer.md"
expect_error "verifier with Write is rejected" "read-only role has write tools" \
  "sed -i.bak 's/^tools: .*/tools: Read, Write/' agents/independent-verifier.md"
expect_error "name != filename is rejected" "!= filename" \
  "sed -i.bak 's/^name: qa-engineer/name: qa/' agents/qa-engineer.md"
expect_error "a preloaded skill that does not exist is rejected" "does not exist under skills/" \
  "rm -rf skills/minimal-diff"
expect_error "a bare (un-namespaced) skill name is rejected" "is not namespaced" \
  "sed -i.bak 's/^  - 100x-engineer:minimal-diff/  - minimal-diff/' agents/code-reviewer.md"
expect_error "a roster agent with no file is rejected" "has no file" \
  "rm agents/rca-investigator.md"
expect_error "an agent outside the roster is rejected" "not in the OPERATING-MODEL" \
  "cp agents/qa-engineer.md agents/extra-agent.md && sed -i.bak 's/^name: qa-engineer/name: extra-agent/' agents/extra-agent.md"
expect_error "a field plugin agents ignore is rejected" "ignored for plugin agents" \
  "sed -i.bak 's/^color: blue/permissionMode: acceptEdits/' agents/backend-engineer.md"
expect_error "a missing tools list is rejected" "no tools list" \
  "sed -i.bak '/^tools:/d' agents/solution-architect.md"
expect_error "a short description is rejected" "under 120" \
  "python3 - <<'PY'
import re,pathlib
p=pathlib.Path('agents/mobile-engineer.md'); t=p.read_text()
t=re.sub(r'description: >\n(  .*\n)+', 'description: Use for mobile.\n', t, count=1); p.write_text(t)
PY"
expect_error "an engineer without the challenge instruction is rejected" "challenge the plan before implementing" \
  "sed -i.bak 's/Challenge the plan before implementing/Think first/' agents/frontend-engineer.md"
expect_error "a body without the operating model is rejected" "OPERATING-MODEL.md" \
  "sed -i.bak 's/OPERATING-MODEL\.md/model.md/g' agents/rca-investigator.md"
expect_error "a body without the baseline is rejected" "100x baseline show" \
  "sed -i.bak 's/100x baseline show/baseline/g' agents/comprehension-mapper.md"
EXTRA="--pending minimal-diff" expect_error "a pending-skill miss is printed apart and still fails" \
  "MISSING-PENDING-SKILL" "rm -rf skills/minimal-diff"

echo
echo "agents: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
