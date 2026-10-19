#!/usr/bin/env bash
# Every `python3 scripts/X.py` referenced in docs or skills must exist and run --help.
# Documentation that names a command which does not exist is worse than no docs: it
# sends the reader down a dead end and erodes trust in everything around it.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PASS=0; FAIL=0
MISSING=""

# collect every referenced script from docs, skills, reviewers and AGENTS.md — both the
# in-repo form `scripts/x.py` and the installed form `100x x`, which bin/100x maps to it
REFS=$( { grep -rhoE 'scripts/[a-z0-9_]+\.py' docs/ skills/ reviewers/ agents/ AGENTS.md README.md 2>/dev/null
          grep -rhoE '(^|[^a-z0-9_/-])100x [a-z][a-z0-9_]+' docs/ skills/ reviewers/ agents/ AGENTS.md README.md 2>/dev/null \
            | sed -E 's/.*100x ([a-z0-9_]+)/scripts\/\1.py/' | grep -vE '^scripts/(engineer|list|root)\.py$'; } \
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

# every concrete `100x plan_feature new ...` / `100x prd new ...` example must run.
# A missing required flag (--tier) made copied examples exit 2. Each runs with
# --dry-run in a scratch repository. Examples with <placeholders>, and prose that
# names the command without a record name, are not runnable and are skipped.
DOCREPO="$(mktemp -d)"; trap 'rm -rf "$DOCREPO"' EXIT
git -C "$DOCREPO" init -q
EXAMPLES="$(mktemp -d)/examples.txt"
python3 - "$EXAMPLES" docs skills reviewers agents AGENTS.md README.md <<'PY'
import pathlib, re, sys
out, seen = [], set()
rx = re.compile(r"100x (?:plan_feature|prd) new [^-\s`][^`\n]*")
for arg in sys.argv[2:]:
    p = pathlib.Path(arg)
    for f in sorted([p] if p.is_file() else p.rglob("*.md")):
        for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            for m in rx.finditer(line):
                cmd = re.split(r"\s+#\s", m.group(0))[0].rstrip(" |\\")
                if "<" in cmd or cmd in seen:
                    continue
                seen.add(cmd)
                out.append(f"{f}:{n}\t{cmd}")
pathlib.Path(sys.argv[1]).write_text("\n".join(out) + ("\n" if out else ""))
PY
NEX=0
while IFS="$(printf '\t')" read -r where cmd; do
  [ -z "$cmd" ] && continue
  NEX=$((NEX+1))
  # shellcheck disable=SC2086 -- word splitting of the documented command is the point
  set -- ${cmd#100x }
  if ( cd "$DOCREPO" && "$ROOT/bin/100x" "$@" --dry-run ) >"$DOCREPO.out" 2>&1; then
    PASS=$((PASS+1)); printf '  ok   %-46s runs: %s\n' "$where" "$cmd"
  else
    FAIL=$((FAIL+1)); printf '  FAIL %-46s exits non-zero: %s\n' "$where" "$cmd"
    sed 's/^/       /' "$DOCREPO.out" | head -4
  fi
done < "$EXAMPLES"
rm -f "$DOCREPO.out" "$EXAMPLES"; rmdir "$(dirname "$EXAMPLES")"
if [ "$NEX" -gt 0 ]; then PASS=$((PASS+1)); printf '  ok   %-46s\n' "$NEX documented new-record examples found"
else FAIL=$((FAIL+1)); printf '  FAIL %-46s\n' "no documented plan_feature/prd new examples found"; fi

echo
[ -n "$MISSING" ] && echo "missing:$MISSING"
echo "docs-commands: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
