#!/usr/bin/env bash
# Regression suite for prd.py: scaffold, audit gates, and PRD<->spec alignment.
# Asserts detection AND absence of false positives.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-54s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-54s\n' "$1"; [ -s $OUT/pd.out ] && sed 's/^/       /' $OUT/pd.out | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" $OUT/pd.out && ok "reports: $1" || bad "does NOT report: $1"; }

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

python3 "$ROOT/scripts/prd.py" new notier --kind auth --stack nestjs >$OUT/pd.out 2>&1
rc_is 2 $? "new: refused without --tier"
has "--tier is required"
[ ! -d "$CONS/docs/engineering/prds/notier" ] && ok "new: nothing written without a tier" || bad "new: wrote a PRD with no tier"

python3 "$ROOT/scripts/prd.py" new demo --kind auth --stack nestjs --tier small >$OUT/pd.out 2>&1
[ -f "$CONS/docs/engineering/prds/demo/prd.md" ] && ok "new: prd.md created in the consumer repo" \
  || bad "new: prd.md not created in the consumer repo"
[ ! -f "$ROOT/prds/demo/prd.md" ] && ok "new: did NOT write into the plugin dir" \
  || bad "new: leaked a prds/ dir into the plugin dir"
has "risk elevated (raised from none by kind)"
has "optional below the growth tier"

python3 "$ROOT/scripts/prd.py" audit "$CONS/docs/engineering/prds/demo" >$OUT/pd.out 2>&1
rc_is 1 $? "audit: fresh PRD fails"
has "placeholder"
has "no out-of-scope"
has "no requirements recorded"
has "likelihood and impact must be integers 1-5"

# A hand-filled baseline PRD — fully passing, so each test below breaks ONE
# rule at a time from a known-good state.
fill_all() {
  cat > "$CONS/docs/engineering/prds/demo/prd.md" <<'MD'
# demo — PRD

| field | value |
|---|---|
| kind | auth |
| stack | nestjs |
| scale tier | small |
| risk | elevated |
| linked spec | specs/demo/spec.md |
| created | 2026-09-29 |
| status | **ready** |

## 1. Problem

| field | answer |
|---|---|
| who has this problem | returning users |
| what they do today | nothing, no login exists |
| what "better" means, measurably | see success metrics |

## 2. Users

| # | segment | current workaround | why they would adopt this |
|---|---|---|
| U1 | returning users | none | to access their account |

## 3. Goals

| # | goal | measured by |
|---|---|---|
| G1 | users can sign in | M1 |

## 4. Success metrics

| # | metric | target (must include a number) | baseline | measurement method | source |
|---|---|---|---|---|---|
| M1 | login success rate | +15% conversion | 20% baseline | tracked via analytics dashboard | user |

## 5. Constraints

| constraint | value | source |
|---|---|---|
| team size and skills | 3 backend engineers, know NestJS | user |
| existing stack | nestjs | code |
| deadline | none stated | user |
| budget | existing infrastructure only | user |
| compliance / regulatory | none | user |
| what cannot change | public API | code |

## 6. Requirements

| # | requirement | why it matters |
|---|---|---|
| R1 | must support email login | core ask |

## 7. Options analysis

| # | option | pros | cons | reversibility x3 | blast radius x3 | moving parts x2 | already-in-use x2 | exit cost x1 | fit (pass/fail) | weighted score |
|---|---|---|---|---|---|---|---|---|---|---|
| O1 | Do nothing / smallest possible change | zero new moving parts | doesn't solve the problem | 5 | 5 | 5 | 5 | 5 | fail | 55 |
| O2 | Build new auth service | flexible | more moving parts to operate | 3 | 3 | 2 | 1 | 3 | pass | 27 |
| O3 | Hosted auth vendor | no password storage | new vendor to operate | 2 | 3 | 2 | 1 | 2 | pass | 23 |

## 8. Recommendation

| field | answer |
|---|---|
| chosen option | O2 |
| single deciding factor | fit |
| what would change it | if do-nothing turned out acceptable |
| override reason (if not the top fit-passing score) | none |

## 9. Design overview

N/A because the design is a single new controller on the existing service.

## 10. Risks

| # | risk | likelihood (1-5) | impact (1-5) | L x I | mitigation | source |
|---|---|---|---|---|---|---|
| RI1 | Adoption is lower than assumed | 3 | 3 | 9 | ship behind a flag to a small cohort first | assumed |
| RI2 | Effort estimate is wrong | 2 | 2 | 4 | timebox phase 1 | assumed |
| RI3 | Existing codebase costs more than scored | 2 | 3 | 6 | spike the riskiest integration point | assumed |

## 11. Phasing

| # | phase | ships | proves | kill criteria | source |
|---|---|---|---|---|---|
| P1 | Phase 1 | email login only | core assumption | conversion stays flat after 2 weeks | assumed |

## 12. Non-goals (out of scope)

| # | explicitly out of scope |
|---|---|
| X1 | MFA is out of scope |

## 13. Security

Throttled login; generic error body.

## 14. Privacy

Email only, single region.

## 15. Observability

Login success and failure counters.

## 16. Rollout / rollback

Flag, then widen; rollback is the flag.

## 17. Migration

N/A because no schema change.

## 18. Test plan

Unit and e2e for login.

## 19. Cost

N/A because no new spend.

## 20. Dependencies

None beyond the existing service.

## 21. Open questions / assumptions

Risk scores are assumed.

## 22. Approvers

Product owner role.

## 23. Existing-code note

No existing code; new feature.
MD
}
P="$CONS/docs/engineering/prds/demo/prd.md"
audit_demo() { python3 "$ROOT/scripts/prd.py" audit "$CONS/docs/engineering/prds/demo" >$OUT/pd.out 2>&1; }

fill_all; audit_demo
rc_is 0 $? "audit: a fully filled PRD passes"
has "PRD is ready"

# --- metric with no number ---
fill_all
swap "$P" "| M1 | login success rate | +15% conversion |" "| M1 | login success rate | improves a lot |"
audit_demo; rc_is 1 $? "audit: metric with no number is rejected"
has "no number in the target"

# --- metric with no measurement method ---
fill_all
swap "$P" "| tracked via analytics dashboard | user |" "| <!-- --> | user |"
audit_demo; rc_is 1 $? "audit: metric with no measurement method is rejected"
has "no measurement method"

# --- source column ---
fill_all
swap "$P" "| tracked via analytics dashboard | user |" "| tracked via analytics dashboard | assumed |"
audit_demo; rc_is 1 $? "audit: assumed target in a ready PRD is rejected"
has "rest on an \`assumed\` source in a \`ready\` PRD"

fill_all
swap "$P" "| budget | existing infrastructure only | user |" "| budget | existing infrastructure only | assumed |"
audit_demo; rc_is 1 $? "audit: assumed constraint in a ready PRD is rejected"

fill_all
swap "$P" "| tracked via analytics dashboard | user |" "| tracked via analytics dashboard | assumed |"
swap "$P" "| status | **ready** |" "| status | **draft** |"
audit_demo; rc_is 0 $? "audit: assumed target allowed while draft"
has "allowed in a draft"

fill_all
swap "$P" "| budget | existing infrastructure only | user |" "| budget | existing infrastructure only | someone said |"
audit_demo; rc_is 1 $? "audit: source outside the allowlist is rejected"
has "no source in user|assumed|default|code"

# --- option with no con ---
fill_all
swap "$P" "| flexible | more moving parts to operate |" "| flexible | <!-- --> |"
audit_demo; rc_is 1 $? "audit: option with no con is rejected"
has "no con"

# --- options table with fewer than 2 real options ---
fill_all
python3 - "$P" <<'PY2'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text()
t = "\n".join(l for l in t.splitlines() if not l.startswith(("| O2 ", "| O3 "))) + "\n"
p.write_text(t)
PY2
audit_demo; rc_is 1 $? "audit: fewer than 2 options is rejected"
has "need >=2"

# --- fit filter and recomputed scores ---
fill_all
swap "$P" "| pass | 27 |" "| pass | 40 |"
audit_demo; rc_is 1 $? "audit: wrong weighted score is rejected"
has "does not match the recomputed 27"

fill_all
swap "$P" "| chosen option | O2 |" "| chosen option | O3 |"
audit_demo; rc_is 1 $? "audit: chosen non-top option without override is rejected"
has "is not the top fit-passing score"

fill_all
swap "$P" "| chosen option | O2 |" "| chosen option | O3 |"
swap "$P" "| override reason (if not the top fit-passing score) | none |" "| override reason (if not the top fit-passing score) | security team mandates a vendor |"
audit_demo; rc_is 0 $? "audit: chosen non-top option WITH override passes"

fill_all
swap "$P" "| chosen option | O2 |" "| chosen option | O1 |"
audit_demo; rc_is 1 $? "audit: chosen option failing the fit filter is rejected"
has "fails the fit filter"

fill_all
swap "$P" "| 5 | fail | 55 |" "| 5 | maybe | 55 |"
audit_demo; rc_is 1 $? "audit: fit must be pass or fail"
has "fit must be pass or fail"

# --- no recommendation ---
fill_all
swap "$P" "| chosen option | O2 |" "| chosen option | <!-- --> |"
audit_demo; rc_is 1 $? "audit: no recommendation is rejected"
has "no recommendation named"

# --- no deciding factor ---
fill_all
swap "$P" "| single deciding factor | fit |" "| single deciding factor | <!-- --> |"
audit_demo; rc_is 1 $? "audit: no deciding factor is rejected"
has "no deciding factor named"

# --- risks ---
fill_all
swap "$P" "| 3 | 3 | 9 | ship behind a flag to a small cohort first |" "| 3 | 3 | 9 | <!-- --> |"
audit_demo; rc_is 1 $? "audit: risk with no mitigation is rejected"
has "no mitigation"

fill_all
swap "$P" "| RI1 | Adoption is lower than assumed | 3 | 3 | 9 |" "| RI1 | Adoption is lower than assumed | high | 3 | 9 |"
audit_demo; rc_is 1 $? "audit: non-numeric risk likelihood is rejected"
has "integers 1-5"

fill_all
swap "$P" "| RI1 | Adoption is lower than assumed | 3 | 3 | 9 |" "| RI1 | Adoption is lower than assumed | 3 | 3 | 12 |"
audit_demo; rc_is 1 $? "audit: wrong L x I is rejected"
has "does not match 9"

# --- no out-of-scope ---
fill_all
swap "$P" "| X1 | MFA is out of scope |" "| X1 | <!-- --> |"
audit_demo; rc_is 1 $? "audit: no out-of-scope is rejected"
has "no out-of-scope items"

# --- design-doc sections ---
fill_all
swap "$P" "Login success and failure counters." ""
audit_demo; rc_is 1 $? "audit: blank design-doc section is rejected"
has "section 'Observability' is blank"

fill_all
swap "$P" "N/A because no new spend." "N/A"
audit_demo; rc_is 1 $? "audit: bare N/A section is rejected"
has "section 'Cost' is blank"

fill_all
swap "$P" "## 22. Approvers" "## 22. Sign-off"
audit_demo; rc_is 1 $? "audit: missing design-doc section is rejected"
has "missing section 'Approvers'"

# --- placeholder in prose, not a table ---
fill_all
swap "$P" "Email only, single region." "<!-- fill in --> Email only."
audit_demo; rc_is 1 $? "audit: placeholder in prose is rejected"
has "placeholder comment"

# --- tier and risk ---
fill_all
swap "$P" "| scale tier | small |" "| scale tier | huge |"
audit_demo; rc_is 1 $? "audit: invalid tier is rejected"
has "a tier must be declared"

fill_all
swap "$P" "| risk | elevated |" "| risk | none |"
audit_demo; rc_is 1 $? "audit: risk below the auth floor is rejected"
has "below the floor"

# restore a passing baseline for the align tests below
fill_all

# ---------- align ----------
# id-level: each AC names the requirement it satisfies; each metric cites a V row.
write_spec() { # write_spec <AC lines> <verification row>
  mkdir -p "$CONS/docs/engineering/specs/demo"
  cat > "$CONS/docs/engineering/specs/demo/spec.md" <<MD
# demo — spec

## 2. In scope / out of scope

| # | in scope | | # | explicitly OUT of scope |
|---|---|---|---|---|
| S1 | email login for returning users | | O1 | signup |

## 2b. Acceptance criteria

$1

## 8. Verification plan

| # | check | command | gate | covers |
|---|---|---|---|---|
$2
MD
}
GOOD_AC="AC-1: A returning user signs in with email and password and gets a session. (R1, S1)"
GOOD_V="| V1 | conversion | manual review of the analytics dashboard | pre-PR | AC-1, M1 |"
ALIGN() { python3 "$ROOT/scripts/prd.py" align "$CONS/docs/engineering/prds/demo" "$CONS/docs/engineering/specs/demo" >$OUT/pd.out 2>&1; }

write_spec "$GOOD_AC" "$GOOD_V"
ALIGN; rc_is 0 $? "align: linked requirement, AC and metric pass clean"
has "id-level tracing"
has "OK    R1"
has "OK    AC-1  -> R1"
has "OK    S1"
has "OK    M1"
has "0 requirement(s) with no spec coverage, 0 spec item(s) implementing nothing in the PRD, 0 metric(s) with no verification step, 0 acceptance criterion/criteria tracing to no requirement"

# a shared word is no longer enough: an AC with no R link traces to nothing
write_spec "AC-1: A returning user signs in with email login and gets a session. (S1)" "$GOOD_V"
ALIGN; rc_is 1 $? "align: AC without an R link is an orphan, keywords do not rescue it"
has "MISS  R1"
has "MISS  AC-1"
has "names no requirement"
has "MISS  S1"
has "1 requirement(s) with no spec coverage, 1 spec item(s) implementing nothing in the PRD, 0 metric(s) with no verification step, 1 acceptance criterion/criteria tracing to no requirement"

# an AC linking a requirement the PRD does not have
write_spec "$GOOD_AC
AC-2: An admin can export the sign-in audit log as CSV. (R7, S1)" "$GOOD_V"
ALIGN; rc_is 1 $? "align: AC naming a requirement absent from the PRD is detected"
has "names R7, not in"

# a metric whose method cites no V row and no row names it
write_spec "$GOOD_AC" "| V1 | unit | npm test | pre-commit | AC-1 |"
ALIGN; rc_is 1 $? "align: metric with no verification row is detected"
has "MISS  M1"
# ...and citing the row from the PRD side clears it
swap "$CONS/docs/engineering/prds/demo/prd.md" "| tracked via analytics dashboard |" "| tracked via analytics dashboard (spec V1) |"
ALIGN; rc_is 0 $? "align: metric citing spec V1 from the PRD passes"
fill_all

# a spec with no acceptance criteria cannot be aligned at all
write_spec "Acceptance: login works." "$GOOD_V"
ALIGN; rc_is 1 $? "align: spec without AC ids fails"
has "defines no acceptance criteria"

# no spec yet: align must not error, and must say so
rm -rf "$CONS/docs/engineering/specs/demo"
ALIGN; rc_is 0 $? "align: no spec yet is not an error"
has "nothing to check"

# ---------- index ----------
python3 "$ROOT/scripts/prd.py" index >$OUT/pd.out 2>&1
rc_is 0 $? "index: regenerates"
[ -f "$CONS/docs/engineering/prds/INDEX.md" ] && ok "index: INDEX.md exists" || bad "index: no INDEX.md"

# ---------- the plugin's own worked example ----------
cd "$ROOT"
python3 "$ROOT/scripts/prd.py" audit "$ROOT/examples/login" >$OUT/pd.out 2>&1
rc_is 0 $? "audit: the worked example (examples/login/prd.md) passes"

python3 "$ROOT/scripts/prd.py" align "$ROOT/examples/login" "$ROOT/specs/login" >$OUT/pd.out 2>&1
rc_is 0 $? "align: the worked example aligns clean against specs/login"
has "0 requirement(s) with no spec coverage, 0 spec item(s) implementing nothing in the PRD, 0 metric(s) with no verification step, 0 acceptance criterion/criteria tracing to no requirement"

# audit_prd is the importable audit plan_feature runs on a spec's linked PRD
python3 - "$ROOT" "$CONS/docs/engineering/prds/demo/prd.md" >$OUT/pd.out 2>&1 <<'PY'
import sys, io, contextlib
sys.path.insert(0, sys.argv[1] + "/scripts")
import prd
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    e, w, info = prd.audit_prd(sys.argv[1] + "/examples/login/prd.md")
    e2, _, info2 = prd.audit_prd(sys.argv[2])
assert buf.getvalue() == "", buf.getvalue()
assert e == [] and info["ready"] and info["status"] == "ready" and info["requirements"] == 5, (e, info)
assert isinstance(e2, list) and isinstance(info2["status"], str), (e2, info2)
PY
rc_is 0 $? "audit_prd: returns (errors, warnings, info) and prints nothing"

echo
echo "prd: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
