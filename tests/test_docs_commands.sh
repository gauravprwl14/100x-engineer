#!/usr/bin/env bash
# Every `python3 scripts/X.py` referenced in docs or skills must exist and run --help.
# Documentation that names a command which does not exist is worse than no docs: it
# sends the reader down a dead end and erodes trust in everything around it.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
MISSING=""

# collect every referenced script from docs, skills, reviewers and AGENTS.md
REFS=$(grep -rhoE 'scripts/[a-z0-9_]+\.py' \
         docs/ skills/ reviewers/ AGENTS.md README.md 2>/dev/null \
       | sort -u)

for s in $REFS; do
  if [ ! -f "$s" ]; then
    FAIL=$((FAIL+1)); printf '  FAIL %-46s referenced but does not exist\n' "$s"
    MISSING="$MISSING $s"; continue
  fi
  if python3 "$s" --help >/dev/null 2>&1 || python3 "$s" -h >/dev/null 2>&1; then
    PASS=$((PASS+1)); printf '  ok   %-46s exists and responds to --help\n' "$s"
  else
    # a tool may legitimately require a subcommand; accept a usage error on bare --help
    out=$(python3 "$s" --help 2>&1 | head -3)
    if echo "$out" | grep -qiE 'usage|positional|required'; then
      PASS=$((PASS+1)); printf '  ok   %-46s exists (subcommand required)\n' "$s"
    else
      FAIL=$((FAIL+1)); printf '  FAIL %-46s exists but --help failed\n' "$s"
      echo "$out" | sed 's/^/       /'
    fi
  fi
done

# every reviewer file referenced by the stack-reviewer skill must exist
for r in $(grep -ohE 'reviewers/[a-z0-9_-]+\.md' skills/stack-reviewer/SKILL.md docs/PLAYBOOK.md 2>/dev/null | sort -u); do
  if [ -f "$r" ]; then PASS=$((PASS+1)); printf '  ok   %-46s exists\n' "$r"
  else FAIL=$((FAIL+1)); printf '  FAIL %-46s referenced but does not exist\n' "$r"; fi
done

echo
[ -n "$MISSING" ] && echo "missing:$MISSING"
echo "docs-commands: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
