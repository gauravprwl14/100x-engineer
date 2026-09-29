#!/usr/bin/env bash
# Regression suite for prd.py: scaffold, audit gates, and PRD<->spec alignment.
# Asserts detection AND absence of false positives.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-54s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-54s\n' "$1"; [ -s /tmp/pd.out ] && sed 's/^/       /' /tmp/pd.out | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF "$1" /tmp/pd.out && ok "reports: $1" || bad "does NOT report: $1"; }

# Literal (non-regex) find-and-replace of one line in a file — avoids sed/perl
# regex-escaping bugs for cells containing '+', '(', '.', etc.
swap() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys, pathlib
f, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(f)
t = p.read_text()
if old not in t:
    print(f"TEST BUG: pattern not found in {f}: {old!r}", file=sys.stderr)
    sys.exit(1)
p.write_text(t.replace(old, new, 1))
PY
}

# ---------- prd.py new/audit, in a CONSUMER repo ----------
# These tools must write into the user's project, not into the installed plugin.
CONS="$TMP/consumer"; mkdir -p "$CONS"; cd "$CONS"
git init -q; git config user.email e@e; git config user.name e
echo x > f.txt; git add -A; git commit -qm init

python3 "$ROOT/scripts/prd.py" new demo --kind auth --stack nestjs >/tmp/pd.out 2>&1
[ -f "$CONS/prds/demo/prd.md" ] && ok "new: prd.md created in the consumer repo" \
  || bad "new: prd.md not created in the consumer repo"
[ ! -f "$ROOT/prds/demo/prd.md" ] && ok "new: did NOT write into the plugin dir" \
  || bad "new: leaked a prds/ dir into the plugin dir"

python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "audit: fresh PRD fails"
has "placeholder"
has "no out-of-scope"
has "no requirements recorded"

# A hand-filled baseline PRD — fully passing, so each test below breaks ONE
# rule at a time from a known-good state.
fill_all() {
  cat > "$CONS/prds/demo/prd.md" <<'MD'
# demo — PRD

| field | value |
|---|---|
| kind | auth |
| stack | nestjs |
| linked spec | specs/demo/spec.md |
| created | 2026-09-29 |
| status | **ready** |

## 1. Problem

| field | answer |
|---|---|
| who has this problem | returning users |
| what they do today | nothing, no login exists |
| what "better" means, measurably | see success metrics |

Users cannot sign back in today.

## 2. Users

| # | segment | current workaround | why they would adopt this |
|---|---|---|
| U1 | returning users | none | to access their account |

## 3. Success metrics

| # | metric | target (must include a number) | baseline | measurement method |
|---|---|---|---|---|
| M1 | login success rate | +15% conversion | 20% baseline | tracked via analytics dashboard |

## 4. Constraints

| constraint | value |
|---|---|
| team size and skills | 3 backend engineers, know NestJS |
| existing stack | nestjs |
| deadline | none stated |
| budget | none stated |
| compliance / regulatory | none |
| what cannot change | public API |

## 5. Requirements

| # | requirement | why it matters |
|---|---|---|
| R1 | must support email login | core ask |

## 6. Options analysis

| # | option | pros | cons | reversibility x3 | blast radius x3 | moving parts x2 | already-in-use x2 | exit cost x1 | fit x1 | weighted score |
|---|---|---|---|---|---|---|---|---|---|---|
| O1 | Do nothing / smallest possible change | zero new moving parts | doesn't solve the problem | 5 | 5 | 5 | 5 | 5 | 1 | 56 |
| O2 | Build new auth service | flexible | more moving parts to operate | 3 | 3 | 2 | 1 | 3 | 5 | 35 |

## 7. Recommendation

| field | answer |
|---|---|
| chosen option | O2 |
| single deciding factor | fit |
| what would change it | if do-nothing turned out acceptable |

## 8. Risks

| # | risk | likelihood (1-5) | impact (1-5) | L x I | mitigation |
|---|---|---|---|---|---|
| RI1 | Adoption is lower than assumed | 3 | 3 | 9 | ship behind a flag to a small cohort first |
| RI2 | Effort estimate is wrong | 2 | 2 | 4 | timebox phase 1 |
| RI3 | Existing codebase costs more than scored | 2 | 3 | 6 | spike the riskiest integration point |

## 9. Phasing

| # | phase | ships | proves | kill criteria |
|---|---|---|---|---|
| P1 | Phase 1 | email login only | core assumption | conversion stays flat after 2 weeks |

## 10. Out of scope

| # | explicitly out of scope |
|---|---|
| X1 | MFA is out of scope |

## 11. Existing-code note

No existing code; new feature.
MD
}

fill_all
python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 0 $? "audit: a fully filled PRD passes"

# --- metric with no number ---
fill_all
swap "$CONS/prds/demo/prd.md" \
  "| M1 | login success rate | +15% conversion | 20% baseline | tracked via analytics dashboard |" \
  "| M1 | login success rate | improves a lot | 20% baseline | tracked via analytics dashboard |"
python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "audit: metric with no number is rejected"
has "no number in the target"

# --- metric with no measurement method ---
fill_all
swap "$CONS/prds/demo/prd.md" \
  "| M1 | login success rate | +15% conversion | 20% baseline | tracked via analytics dashboard |" \
  "| M1 | login success rate | +15% conversion | 20% baseline | <!-- --> |"
python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "audit: metric with no measurement method is rejected"
has "no measurement method"

# --- option with no con ---
fill_all
swap "$CONS/prds/demo/prd.md" \
  "| O2 | Build new auth service | flexible | more moving parts to operate | 3 | 3 | 2 | 1 | 3 | 5 | 35 |" \
  "| O2 | Build new auth service | flexible | <!-- --> | 3 | 3 | 2 | 1 | 3 | 5 | 35 |"
python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "audit: option with no con is rejected"
has "no con"

# --- options table with fewer than 2 real options ---
fill_all
swap "$CONS/prds/demo/prd.md" \
  "| O2 | Build new auth service | flexible | more moving parts to operate | 3 | 3 | 2 | 1 | 3 | 5 | 35 |" \
  "| O2 | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> |"
python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "audit: fewer than 2 options is rejected"
has "need >=2"

# --- no recommendation ---
fill_all
swap "$CONS/prds/demo/prd.md" "| chosen option | O2 |" "| chosen option | <!-- --> |"
python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "audit: no recommendation is rejected"
has "no recommendation named"

# --- no deciding factor ---
fill_all
swap "$CONS/prds/demo/prd.md" "| single deciding factor | fit |" "| single deciding factor | <!-- --> |"
python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "audit: no deciding factor is rejected"
has "no deciding factor named"

# --- risk with no mitigation ---
fill_all
swap "$CONS/prds/demo/prd.md" \
  "| RI1 | Adoption is lower than assumed | 3 | 3 | 9 | ship behind a flag to a small cohort first |" \
  "| RI1 | Adoption is lower than assumed | 3 | 3 | 9 | <!-- --> |"
python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "audit: risk with no mitigation is rejected"
has "no mitigation"

# --- no out-of-scope ---
fill_all
swap "$CONS/prds/demo/prd.md" "| X1 | MFA is out of scope |" "| X1 | <!-- --> |"
python3 "$ROOT/scripts/prd.py" audit "$CONS/prds/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "audit: no out-of-scope is rejected"
has "no out-of-scope items"

# restore a passing baseline for the align tests below
fill_all

# ---------- align ----------
mkdir -p "$CONS/specs/demo"
cat > "$CONS/specs/demo/spec.md" <<'MD'
# demo — spec

## 2. In scope / out of scope

| # | in scope | | # | explicitly OUT of scope |
|---|---|---|---|---|
| S1 | email login for returning users | | O1 | signup |

## 8. Verification plan

| # | check | command | gate |
|---|---|---|---|
| V1 | conversion dashboard check | manual review of the analytics dashboard | pre-PR |
MD

python3 "$ROOT/scripts/prd.py" align "$CONS/prds/demo" "$CONS/specs/demo" >/tmp/pd.out 2>&1
rc_is 0 $? "align: matched requirement and metric pass clean"
has "keyword-level matching"
has "0 requirement(s) with no spec coverage"

# no spec yet: align must not error, and must say so
rm -rf "$CONS/specs/demo"
python3 "$ROOT/scripts/prd.py" align "$CONS/prds/demo" "$CONS/specs/demo" >/tmp/pd.out 2>&1
rc_is 0 $? "align: no spec yet is not an error"
has "nothing to check"

# an intentionally unmatched requirement must be detected
mkdir -p "$CONS/specs/demo"
cat > "$CONS/specs/demo/spec.md" <<'MD'
# demo — spec

## 2. In scope / out of scope

| # | in scope | | # | explicitly OUT of scope |
|---|---|---|---|---|
| S1 | email login for returning users | | O1 | signup |

## 8. Verification plan

| # | check | command | gate |
|---|---|---|---|
| V1 | conversion dashboard check | manual review of the analytics dashboard | pre-PR |
MD
swap "$CONS/prds/demo/prd.md" \
  "| R1 | must support email login | core ask |" \
  "| R1 | must support hardware security key WebAuthn | zzz |"
python3 "$ROOT/scripts/prd.py" align "$CONS/prds/demo" "$CONS/specs/demo" >/tmp/pd.out 2>&1
rc_is 1 $? "align: an unmatched requirement is detected"
has "MISS  R1"
has "1 requirement(s) with no spec coverage"

# ---------- index ----------
python3 "$ROOT/scripts/prd.py" index >/tmp/pd.out 2>&1
rc_is 0 $? "index: regenerates"
[ -f "$CONS/prds/INDEX.md" ] && ok "index: INDEX.md exists" || bad "index: no INDEX.md"

# ---------- the plugin's own worked example ----------
cd "$ROOT"
python3 "$ROOT/scripts/prd.py" audit "$ROOT/examples/login" >/tmp/pd.out 2>&1
rc_is 0 $? "audit: the worked example (examples/login/prd.md) passes"

python3 "$ROOT/scripts/prd.py" align "$ROOT/examples/login" "$ROOT/specs/login" >/tmp/pd.out 2>&1
rc_is 0 $? "align: the worked example aligns clean against specs/login"
has "0 requirement(s) with no spec coverage, 0 spec item(s) implementing nothing in the PRD, 0 metric(s) with no verification step"

echo
echo "prd: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
