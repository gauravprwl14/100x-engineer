#!/usr/bin/env bash
# Regression suite for scripts/check_index.py's term index (--gen-terms / --check-terms)
# and catalogue registration (--register). Detection AND no false positives, in a
# throwaway consumer repo.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
CI="$ROOT/scripts/check_index.py"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-60s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-60s\n' "$1"; [ -s $OUT/c.out ] && sed 's/^/       /' $OUT/c.out | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" "${2:-$OUT/c.out}" && ok "has: $1" || bad "missing: $1"; }
no()   { grep -qF -- "$1" "${2:-$OUT/c.out}" && bad "false positive: $1" || ok "absent: $1"; }

C="$TMP/consumer"; mkdir -p "$C/docs" "$C/skills/x"; cd "$C"
git init -q; git config user.email e@e; git config user.name e

cat > docs/guide.md <<'MD'
# Guide

## Contents

| section | answers |
|---|---|

## 1. Roles & owners

The **hot file** is the most-connected file a request passes through.

## Agent protocol

A **Receipt** — a signed record binding a check to the exact code it ran on.

## Agent protocol

**Two-way door**: a decision that is cheap to reverse.

### Error budget

```markdown
## Not A Heading Inside A Fence
**Fenced Bold** — not a definition either
```

## Glossary

| term | meaning |
|---|---|
| **Tenant** | one customer company |
| `companyId` | the tenant key |

## Overview

Plain prose with **emphasis** in the middle of a sentence and **"code": 1** mentioned.
MD
cat > skills/x/SKILL.md <<'MD'
# X

## Error Budget

**error budget** — how much unreliability the SLO allows.
MD
printf "# Skill index\n" > skills/INDEX.md
for i in $(seq 1 9); do printf '# D%s\n\n## Checklist\n\nx\n' "$i" > "docs/d$i.md"; done
git add -A; git commit -qm init

python3 "$CI" --gen-terms >$OUT/c.out 2>&1
rc_is 0 $? "gen-terms: exits 0 on a clean repo"
[ -f TERMS.md ] && ok "gen-terms: TERMS.md written at the root" || bad "gen-terms: no TERMS.md"
T="$C/TERMS.md"

# extraction
has "**hot file** — [docs/guide.md#1-roles--owners](docs/guide.md#1-roles--owners) *defined*" "$T"
has "**Receipt** — [docs/guide.md#agent-protocol](docs/guide.md#agent-protocol) *defined*" "$T"
has "**Two-way door** — [docs/guide.md#agent-protocol-1](docs/guide.md#agent-protocol-1) *defined*" "$T"
has "**Roles & owners** — [docs/guide.md#1-roles--owners]" "$T"
has "**Tenant** — [docs/guide.md#glossary](docs/guide.md#glossary) *defined*" "$T"
has "**companyId** — [docs/guide.md#glossary]" "$T"
has "[docs/guide.md#agent-protocol-1](docs/guide.md#agent-protocol-1)" "$T"

# case-insensitive dedupe: heading in two files + a bold definition -> one entry, defined form wins
n=$(grep -ci '^- \*\*error budget\*\*' "$T")
[ "$n" -eq 1 ] && ok "dedupe: 'Error budget' / 'Error Budget' / 'error budget' -> one entry" \
  || bad "dedupe: $n entries for error budget"
grep -i '^- \*\*error budget\*\*' "$T" | grep -q 'skills/x/SKILL.md#error-budget) \*defined\*' \
  && grep -i '^- \*\*error budget\*\*' "$T" | grep -q 'docs/guide.md#error-budget' \
  && ok "dedupe: every place the term appears is listed" || bad "dedupe: references lost"

# filters
no "**Contents**" "$T"
no "**Overview**" "$T"
no "**Glossary**" "$T"
no "Not A Heading Inside A Fence" "$T"
no "Fenced Bold" "$T"
no "**emphasis**" "$T"
no '"code"' "$T"
no "**Checklist**" "$T"
grep -q '^## E$' "$T" && grep -q '^## T$' "$T" && ok "letter sections present" || bad "letter sections missing"

# links are relative to TERMS.md and every anchor exists
python3 - "$C" "$CI" <<'PY' >$OUT/c.out 2>&1
import re, sys, pathlib
root = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(pathlib.Path(sys.argv[2]).parent))
import check_index as ci
t = (root / "TERMS.md").read_text()
for f, a in re.findall(r"\]\(([^)#]+)#([^)]+)\)", t):
    heads, seen, fence = set(), {}, False
    for l in (root / f).read_text().splitlines():
        if l.lstrip().startswith("```"): fence = not fence; continue
        m = None if fence else re.match(r"^(#{1,6})\s+(.+?)\s*$", l)
        if m:
            b = ci.gh_slug(m.group(2)); n = seen.get(b, 0); seen[b] = n + 1
            heads.add(b if n == 0 else f"{b}-{n}")
    assert a in heads, (f, a, heads)
print("all anchors resolve")
PY
rc_is 0 $? "anchors: every TERMS.md link resolves to a heading anchor"

# --check-terms
python3 "$CI" --check-terms >$OUT/c.out 2>&1
rc_is 0 $? "check-terms: passes right after generation"
has "is current"
printf '\n## Idempotency key\n\nx\n' >> docs/guide.md
python3 "$CI" --check-terms >$OUT/c.out 2>&1
rc_is 1 $? "check-terms: fails once a doc gains a term"
has "TERMS.md is stale"
python3 "$CI" --gen-terms >/dev/null 2>&1
python3 "$CI" --check-terms >$OUT/c.out 2>&1
rc_is 0 $? "check-terms: passes again after regeneration"
mv TERMS.md TERMS.bak
python3 "$CI" --check-terms >$OUT/c.out 2>&1
rc_is 1 $? "check-terms: fails when TERMS.md is missing"
has "TERMS.md is missing"
mv TERMS.bak TERMS.md

# configurable roots and output (the docs/engineering layout of a user project)
mkdir -p docs/engineering/architecture
printf '# Architecture: auth\n\nHow sign-in reaches the session store.\n\n## Session store\n\nx\n' \
  > docs/engineering/architecture/auth.md
python3 "$CI" --gen-terms --terms-root docs/engineering --terms-out docs/engineering/TERMS.md >$OUT/c.out 2>&1
rc_is 0 $? "gen-terms: custom root and output"
has "**Session store** — [docs/engineering/architecture/auth.md#session-store](architecture/auth.md#session-store)" docs/engineering/TERMS.md
no "Receipt" docs/engineering/TERMS.md
python3 "$CI" --check-terms --terms-root docs/engineering --terms-out docs/engineering/TERMS.md >$OUT/c.out 2>&1
rc_is 0 $? "check-terms: custom root and output are current"

# --register
python3 "$CI" --register docs/engineering/architecture/auth.md >$OUT/c.out 2>&1
rc_is 0 $? "register: exits 0"
has "| [Architecture: auth](architecture/auth.md) | architecture | How sign-in reaches the session store. |" docs/engineering/INDEX.md
printf '# Architecture: auth\n\nHow sign-in and refresh reach the session store.\n' > docs/engineering/architecture/auth.md
python3 "$CI" --register docs/engineering/architecture/auth.md >$OUT/c.out 2>&1
has "updated architecture/auth.md"
[ "$(grep -c 'architecture/auth.md' docs/engineering/INDEX.md)" -eq 1 ] \
  && ok "register: second run updates the row, no duplicate" || bad "register: duplicated row"
has "sign-in and refresh" docs/engineering/INDEX.md
python3 "$CI" --register docs/engineering/architecture/nope.md >$OUT/c.out 2>&1
rc_is 2 $? "register: a missing file exits 2"

# existing behaviour intact: plain check passes on this small repo
python3 "$CI" >$OUT/c.out 2>&1
rc_is 0 $? "plain check: unchanged behaviour on a repo with nothing to index"

# generated records: a spec.md / prd.md carrying its generator's header table is a
# fixed-structure file (AGENTS.md rule 17); anything else that long still needs Contents
python3 "$ROOT/scripts/plan_feature.py" new big --tier growth --risk regulated \
  --work api,web-ui,mobile,data-pipeline,iac >/dev/null 2>&1
python3 "$ROOT/scripts/prd.py" new big --kind crud --tier growth >/dev/null 2>&1
S="docs/engineering/specs/big/spec.md"; P="docs/engineering/prds/big/prd.md"
[ "$(wc -l < "$S")" -ge 150 ] && [ "$(wc -l < "$P")" -ge 150 ] \
  && ok "fixture: generated spec and PRD are long enough to be checked" \
  || bad "fixture: a generated record under 150 lines leaves the exemption untested"
python3 "$CI" docs/engineering >$OUT/c.out 2>&1
rc_is 0 $? "generated spec.md and prd.md need no Contents table"
no "MISSING"
python3 - "$S" <<'PY'
import sys, pathlib, re
p = pathlib.Path(sys.argv[1]); t = p.read_text()
p.write_text(re.sub(r"^\| field \| value \|\n\|---\|---\|\n", "", t, count=1, flags=re.M))
PY
python3 "$CI" docs/engineering >$OUT/c.out 2>&1
rc_is 1 $? "a spec.md whose generator header was removed needs Contents again"
has "MISSING  docs/engineering/specs/big/spec.md"
mkdir -p docs/engineering/specs/notes
cp "$P" docs/engineering/specs/notes/design.md
python3 "$CI" docs/engineering/specs/notes >$OUT/c.out 2>&1
rc_is 1 $? "a long hand-named doc under specs/ is not exempt"

cd "$ROOT"
echo
echo "check_index: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
