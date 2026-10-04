#!/usr/bin/env bash
# End-to-end: PRD -> spec with acceptance criteria -> alignment -> test plan -> task
# graph -> tagged tests -> decision -> ledger, in a fresh repo with NO .100x.json, every
# call through the `100x` dispatcher. Proves the AC id is one join key across all the
# tools and that every record lands under the default root, docs/engineering/.
# Then the root resolver on its own: config, env, precedence, refusal, legacy layout.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
X="$ROOT/bin/100x"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-62s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-62s\n' "$1"; [ -s $OUT/e.out ] && sed 's/^/       /' $OUT/e.out | head -12; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" $OUT/e.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -qF -- "$1" $OUT/e.out && bad "false positive: $1" || ok "absent: $1"; }
run()  { "$X" "$@" >$OUT/e.out 2>&1; }

newrepo() { mkdir -p "$1" && cd "$1" && git init -q && git config user.email e@e \
  && git config user.name e && echo x > f.txt && git add -A && git commit -qm init; }

R="$TMP/app"; newrepo "$R"
E="docs/engineering"

# ---------------------------------------------------------------- 1. PRD
run prd new login --kind auth --stack nestjs --tier small
rc_is 0 $? "prd new: exits 0"
[ -f "$E/prds/login/prd.md" ] && ok "prd new: written under $E/prds/" || bad "prd new: not under $E"

cat > "$E/prds/login/prd.md" <<'MD'
# login — PRD

| field | value |
|---|---|
| kind | auth |
| stack | nestjs |
| scale tier | small |
| risk | elevated |
| linked spec | docs/engineering/specs/login/spec.md |
| created | 2026-10-01 |
| status | **ready** |

## 1. Problem

| field | answer |
|---|---|
| who has this problem | returning users |
| what they do today | nothing, no login exists |
| what "better" means, measurably | see success metrics |

## 2. Users

| # | segment | current workaround | why they would adopt this |
|---|---|---|---|
| U1 | returning users | none | to reach their account |

## 3. Goals

| # | goal | measured by |
|---|---|---|
| G1 | users can sign in and out | M1 |

## 4. Success metrics

| # | metric | target (must include a number) | baseline | measurement method | source |
|---|---|---|---|---|---|
| M1 | sign-in success | 99% of valid sign-ins succeed | N/A, new feature | the e2e suite (spec V3) | user |

## 5. Constraints

| constraint | value | source |
|---|---|---|
| team size and skills | 2 backend engineers, know NestJS | user |
| existing stack | nestjs | code |
| deadline | none stated | user |
| budget | existing infrastructure only | user |
| compliance / regulatory | none | user |
| what cannot change | public API | code |

## 6. Requirements

| # | requirement | why it matters |
|---|---|---|
| R1 | returning users sign in with email and password | the core ask |
| R2 | logout ends the session immediately | a session that outlives logout is a security hole |

## 7. Options analysis

| # | option | pros | cons | reversibility x3 | blast radius x3 | moving parts x2 | already-in-use x2 | exit cost x1 | fit (pass/fail) | weighted score |
|---|---|---|---|---|---|---|---|---|---|---|
| O1 | Do nothing / smallest possible change | zero new moving parts | does not solve the problem | 5 | 5 | 5 | 5 | 5 | fail | 55 |
| O2 | Session module in the existing service | one deploy | owns password storage | 4 | 3 | 3 | 4 | 4 | pass | 39 |

## 8. Recommendation

| field | answer |
|---|---|
| chosen option | O2 |
| single deciding factor | the only fit-passing option |
| what would change it | a mandate to use a hosted identity vendor |
| override reason (if not the top fit-passing score) | none |

## 9. Design overview

N/A because it is one controller and one service on the existing app.

## 10. Risks

| # | risk | likelihood (1-5) | impact (1-5) | L x I | mitigation | source |
|---|---|---|---|---|---|---|
| RI1 | brute force on the endpoint | 3 | 3 | 9 | per-account throttling | user |

## 11. Phasing

| # | phase | ships | proves | kill criteria | source |
|---|---|---|---|---|---|
| P1 | Phase 1 | email sign-in and logout | the session model | sign-in error rate above 1% | user |

## 12. Non-goals (out of scope)

| # | explicitly out of scope |
|---|---|
| X1 | MFA |

## 13. Security

Throttled sign-in, generic error body, httpOnly cookie.

## 14. Privacy

Email and password hash only, existing region.

## 15. Observability

Sign-in success and failure counters.

## 16. Rollout / rollback

Behind a flag; rollback is the flag.

## 17. Migration

N/A because the sessions table is new and additive.

## 18. Test plan

Unit and e2e per acceptance criterion.

## 19. Cost

N/A because no new spend.

## 20. Dependencies

None beyond the existing service.

## 21. Open questions / assumptions

None open.

## 22. Approvers

Product owner role.

## 23. Existing-code note

Written before the code.
MD
run prd audit "$E/prds/login"
rc_is 0 $? "prd audit: the filled PRD is ready"
has "PRD is ready"

# ---------------------------------------------------------------- 2. spec
run plan_feature new login --kind crud --tier small --work api
rc_is 0 $? "plan_feature new: exits 0"
S="$E/specs/login/spec.md"
[ -f "$S" ] && ok "plan_feature new: written under $E/specs/" || bad "plan_feature new: not under $E"
grep -q "^| prd | $E/prds/login |" "$S" && ok "plan_feature new: header links the existing PRD" \
  || bad "plan_feature new: PRD not linked in the header"

# before the ACs are written, align must fail on the placeholder criterion
run prd align "$E/prds/login" "$E/specs/login"
rc_is 1 $? "prd align: scaffolded spec (placeholder AC) does not align"

python3 - "$S" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1]); t = p.read_text()
t = re.sub(r"^\| S1 \| <!-- --> \|.*$",
           "| S1 | email + password sign-in | | O1 | registration |\n"
           "| S2 | logout of the current session | | O2 | MFA |", t, count=1, flags=re.M)
t = t.replace("AC-1: <!-- observable outcome --> (R1, S1)",
  "AC-1: A user with a correct email and password gets a 204 and a session cookie. (R1, S1)\n"
  "AC-2: A wrong password returns 401 with the same body as an unknown email. (R1, S1)\n"
  "AC-3: After logout, a request carrying the ended session gets 401. (R2, S2)")
t = re.sub(r"\| V1 \| types .*?\| V4 \| the edge cases above \|[^\n]*\n",
  "| V1 | types | `npx tsc --noEmit` | pre-commit | — |\n"
  "| V2 | unit | `npx jest unit` | pre-commit | AC-1, AC-2 |\n"
  "| V3 | e2e | `npx jest e2e` | pre-PR | AC-1, AC-2, AC-3 |\n"
  "| V4 | every AC has a tagged test | `100x testplan trace docs/engineering/specs/login/spec.md --tests tests` | pre-PR | AC-1, AC-2, AC-3 |\n",
  t, count=1, flags=re.S)
p.write_text(t)
PY
grep -c "^AC-[0-9]*: " "$S" | grep -qx 3 && ok "spec: three acceptance criteria written" || bad "spec: AC fill failed"

# the AC rules pass even though the rest of the spec (baseline, edge cases) is unfilled
run plan_feature audit "$E/specs/login"
has "acceptance : 3 criteria"
no "acceptance criteri"
no "in-scope item"
no "verification row covers"

run prd align "$E/prds/login" "$E/specs/login"
rc_is 0 $? "prd align: R1, R2 <-> AC-1..3 <-> S1, S2 and M1 -> V3 all trace"
has "OK    R2  logout ends the session immediately  <- AC-3"
has "OK    M1"
has "0 requirement(s) with no spec coverage, 0 spec item(s) implementing nothing in the PRD, 0 metric(s) with no verification step, 0 acceptance criterion/criteria tracing to no requirement"

# ---------------------------------------------------------------- 3. test plan
run testplan new "$S"
rc_is 0 $? "testplan new: exits 0"
has "3 acceptance criteria"
for ac in AC-1 AC-2 AC-3; do
  grep -qE "^\| TC-[0-9]+-1 \| login/$ac \|" $OUT/e.out && ok "testplan new: cases for login/$ac" || bad "testplan new: no case for login/$ac"
done
run testplan new "$S" --out
rc_is 0 $? "testplan new --out: exits 0"
[ -f "$E/testplans/login.md" ] && ok "testplan --out: default path under $E/testplans/" \
  || bad "testplan --out: default path not under $E"

# ---------------------------------------------------------------- 4. task graph
PLAN="$E/specs/login/plan.json"
cat > "$PLAN" <<'JSON'
{"schema": 1, "feature": "login", "tier": "small", "tasks": [
  {"id": "T0", "title": "auth DTO contract", "owner": "backend-engineer", "depends_on": [],
   "files": ["src/auth/dto/**"], "acceptance": ["AC-1"], "verify": ["test -d src/auth/dto"], "contract": true},
  {"id": "T1", "title": "session service", "owner": "backend-engineer", "depends_on": ["T0"],
   "consumes": ["T0"], "files": ["src/auth/service/**"], "acceptance": ["AC-1", "AC-2"],
   "verify": ["test -f src/auth/service/session.service.ts"]},
  {"id": "T2", "title": "logout + e2e", "owner": "qa-engineer", "depends_on": ["T1"],
   "files": ["tests/**"], "acceptance": ["AC-3"], "verify": ["test -f tests/login.test.ts"]}
]}
JSON
run plan_dag lint "$PLAN" --spec "$S"
rc_is 0 $? "plan_dag lint --spec: every AC owned by a task"
python3 - "$PLAN" "$OUT/gap.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["tasks"][2]["acceptance"] = ["AC-1"]
json.dump(d, open(sys.argv[2], "w"))
PY
run plan_dag lint "$OUT/gap.json" --spec "$S"
rc_is 1 $? "plan_dag lint --spec: a plan dropping AC-3 fails"
has "AC-3 in $S is covered by no task"

# ---------------------------------------------------------------- 5. trace
mkdir -p tests
cat > tests/login.test.ts <<'TS'
test('login/AC-1 signs in with a valid password', async () => { expect(await login()).toBe(204); });
test('billing/AC-2 a different feature numbered the same', () => { expect(1).toBe(1); });
test('AC-3 a bare id names no feature', () => { expect(1).toBe(1); });
TS
run testplan trace "$S" --tests tests
rc_is 1 $? "testplan trace: only login/AC-1 tagged fails"
has "uncovered: AC-2, AC-3"
has "1 tag(s) for other features ignored"
has "HINT 1 bare AC-<n> tag(s) not counted"
cat >> tests/login.test.ts <<'TS'
test('login/AC-2 wrong password is a generic 401', async () => { expect(await bad()).toBe(401); });
test('login/AC-3 ended session is refused', async () => { expect(await after()).toBe(401); });
TS
run testplan trace "$S" --tests tests
rc_is 0 $? "testplan trace: all three tagged passes"
has "3/3 ACs covered"


# ---------------------------------------------------------------- 5b. every gate command as written
# The router (skills/100x), the agents and docs/OPERATING-MODEL.md write record
# arguments in several shapes; in a project with no .100x.json every one must reach
# the record under docs/engineering/, never exit 2 for resolving against the repo top.
[ ! -e .100x.json ] && ok "gates: this repo has no .100x.json" || bad "gates: unexpected .100x.json"
for args in "prd audit $E/prds/login" "prd audit prds/login" "prd audit login"; do
  run $args; rc_is 0 $? "gate: 100x $args"
done
for args in "prd align $E/prds/login $E/specs/login" "prd align prds/login specs/login" "prd align login login"; do
  run $args; rc_is 0 $? "gate: 100x $args"
done
for args in "plan_feature audit $E/specs/login" "plan_feature audit specs/login" "plan_feature audit login" \
            "plan_feature audit $S"; do
  run $args; rc=$?
  [ "$rc" -eq 1 ] && grep -q "acceptance : 3 criteria" $OUT/e.out && ok "gate: 100x $args audits the spec (exit 1: unfilled)" \
    || bad "gate: 100x $args (exit $rc)"
done
(cd tests && "$X" plan_feature audit specs/login >$OUT/e.out 2>&1); rc=$?
[ "$rc" -eq 1 ] && ok "gate: plan_feature audit specs/login from a subdirectory" || bad "gate: from a subdirectory (exit $rc)"
for args in "testplan new $S" "testplan new specs/login/spec.md" "testplan new login" \
            "testplan trace $S --tests tests" "testplan trace specs/login/spec.md --tests tests" \
            "testplan trace login --tests tests" \
            "plan_dag lint $PLAN --spec $S" "plan_dag lint $PLAN --spec specs/login/spec.md" \
            "plan_dag lint $PLAN --spec login" "plan_dag waves $PLAN" "plan_dag next $PLAN"; do
  run $args; rc_is 0 $? "gate: 100x $args"
done

# per task: the agent works in its own worktree; lint and replay check it there
git worktree add -q "$TMP/wt-T1" 2>/dev/null
mkdir -p "$TMP/wt-T1/src/auth/service"
echo 'export class SessionService {}' > "$TMP/wt-T1/src/auth/service/session.service.ts"
cat > "$OUT/T1.md" <<'MD'
Done.

```json
{"schema": 1, "agent": "backend-engineer", "task_id": "T1", "status": "done",
 "understanding": "Session service for sign-in.", "inputs_read": ["docs/engineering/specs/login/spec.md"],
 "assumptions": [], "questions": [], "plan_issues": [], "decisions": [],
 "changes": [{"path": "src/auth/service/session.service.ts", "summary": "service"}],
 "evidence": [{"cmd": "test -f src/auth/service/session.service.ts", "exit_code": 0, "output_tail": ""}],
 "follow_ups": []}
```
MD
run agent_report extract "$OUT/T1.md" -o "$OUT/T1.json"; rc_is 0 $? "gate: 100x agent_report extract msg.md -o T1.json"
run agent_report lint "$OUT/T1.json" --graph "$PLAN" --cwd "$TMP/wt-T1"
rc_is 0 $? "gate: 100x agent_report lint T1.json --graph plan.json --cwd ../wt-T1"
run agent_report replay "$OUT/T1.json" --graph "$PLAN" --cwd "$TMP/wt-T1" --yes
rc_is 0 $? "gate: 100x agent_report replay T1.json --graph plan.json --cwd ../wt-T1 --yes"
has "1/1 reproduced"
# the old form, with no plan, is refused rather than running report text
run agent_report replay "$OUT/T1.json" --cwd "$TMP/wt-T1" --yes
rc_is 2 $? "gate: replay without --graph is refused (exit 2)"
# a hollow report: the same claims against a worktree where nothing changed
git worktree add -q "$TMP/wt-hollow" 2>/dev/null
run agent_report lint "$OUT/T1.json" --graph "$PLAN" --cwd "$TMP/wt-hollow"
rc_is 1 $? "gate: a hollow report (claimed change absent) is rejected"
has "is claimed but the worktree has no change"
git worktree remove --force "$TMP/wt-hollow" 2>/dev/null
git worktree remove --force "$TMP/wt-T1" 2>/dev/null

# ---------------------------------------------------------------- 6. decision
run decide new "Session store for login" --affects "src/auth/**" --tag login
rc_is 0 $? "decide new: exits 0"
ADR="$(ls $E/decisions/ADR-0001-*.md 2>/dev/null | head -1)"
[ -n "$ADR" ] && ok "decide new: written under $E/decisions/" || bad "decide new: not under $E"
run decide lint
rc_is 1 $? "decide lint: the unfilled template is rejected"
python3 - "$ADR" <<'PY'
import json, pathlib, re, sys
p = pathlib.Path(sys.argv[1]); t = p.read_text()
m = re.search(r"```json meta\n(.*?)\n```", t, re.S)
meta = json.loads(m.group(1))
meta["options"] = [
  {"name": "signed cookie only", "fit": "fail", "chosen": False,
   "why_not": "cannot be revoked at logout, so AC-3 fails"},
  {"name": "server-side session row", "fit": "pass", "chosen": True,
   "why": "logout deletes the row, satisfying AC-3"}]
meta["assumptions"] = [{"id": "A1", "claim": "the existing database is reachable from the app",
                        "verify": "true", "revisit_when": "sessions move to an edge runtime",
                        "confidence": "high"}]
p.write_text(t[:m.start(1)] + json.dumps(meta, indent=2) + t[m.end(1):])
PY
run decide lint
rc_is 0 $? "decide lint: the filled record (fit-passing choice) passes"

# ---------------------------------------------------------------- 7. ledger
run ledger index
rc_is 0 $? "ledger index: exits 0"
run ledger map
rc_is 0 $? "ledger map: exits 0"
[ -f "$E/ledger/INDEX.md" ] && [ -f "$E/ledger/MAP.md" ] && ok "ledger: INDEX.md and MAP.md under $E/ledger/" \
  || bad "ledger: index files not under $E"
grep -E "^\| \*\*login\*\* \|" "$E/ledger/MAP.md" | grep -q "ADR-0001" \
  && grep -E "^\| \*\*login\*\* \|" "$E/ledger/MAP.md" | grep -q "prd.md" \
  && ok "ledger map: login row pairs its PRD, spec and ADR" || bad "ledger map: login row incomplete"
grep -q "](../specs/login/spec.md)" "$E/ledger/INDEX.md" && ok "ledger index: links are page-relative" \
  || bad "ledger index: links not page-relative"

# ---------------------------------------------------------------- 8. nothing at the top
top="$(ls -A | sort | tr '\n' ' ')"
[ "$top" = ".git docs f.txt tests " ] && ok "repo top level holds only docs/ (+ the test's own files)" \
  || { echo "$top" > $OUT/e.out; bad "repo top level gained entries: $top"; }
for d in prds specs decisions rca lessons ledger testplans reviews; do
  [ -e "$d" ] && bad "a $d/ directory appeared at the top level"
done

# ================================================================ resolver
cd "$TMP"

# config file
newrepo "$TMP/cfg"; printf '{"root": "eng/records"}\n' > .100x.json
run decide new "A choice"
[ -f eng/records/decisions/ADR-0001-a-choice.md ] && ok "root: .100x.json root is used" \
  || bad "root: .100x.json ignored"
[ ! -e docs ] && ok "root: nothing written to the default root" || bad "root: default root used despite config"

# environment variable
newrepo "$TMP/env"
HUNDREDX_ROOT_DIR=records "$X" decide new "A choice" >$OUT/e.out 2>&1
[ -f records/decisions/ADR-0001-a-choice.md ] && ok "root: HUNDREDX_ROOT_DIR is used without a config" \
  || bad "root: HUNDREDX_ROOT_DIR ignored"

# config outranks the environment
newrepo "$TMP/both"; printf '{"root": "from-config"}\n' > .100x.json
HUNDREDX_ROOT_DIR=from-env "$X" decide new "A choice" >$OUT/e.out 2>&1
[ -d from-config/decisions ] && [ ! -e from-env ] && ok "root: .100x.json outranks HUNDREDX_ROOT_DIR" \
  || bad "root: precedence wrong"

# a root that leaves the repository is refused, and nothing is written
newrepo "$TMP/esc"
for bad_root in '"../outside"' '"/tmp/abs"' '""' '5'; do
  printf '{"root": %s}\n' "$bad_root" > .100x.json
  run decide new "Escape"
  rc_is 2 $? "root: config root $bad_root refused"
done
printf '{not json\n' > .100x.json
run decide new "Escape"; rc_is 2 $? "root: malformed .100x.json refused"
has "not valid JSON"
[ ! -e "$TMP/outside" ] && [ -z "$(find . -name 'ADR-*' -not -path './.git/*')" ] \
  && ok "root: nothing written by a refused root" || bad "root: a refused root still wrote"
rm .100x.json
HUNDREDX_ROOT_DIR=../outside "$X" decide new "Escape" >$OUT/e.out 2>&1
rc_is 2 $? "root: HUNDREDX_ROOT_DIR escaping the repo refused"

# legacy layout: existing top-level records keep working, with a warning
newrepo "$TMP/legacy"; mkdir -p decisions
cp "$ROOT/decisions/ADR-0001-session-strategy-for-login.md" decisions/
run decide index
rc_is 0 $? "legacy: decide index still works"
has "warning: using the legacy top-level record directories (decisions/)"
[ -f decisions/INDEX.md ] && [ ! -e docs ] && ok "legacy: kept writing to the top-level decisions/" \
  || bad "legacy: stranded the existing records"
run ledger index
grep -q "ADR-0001" decisions/INDEX.md && [ -f ledger/INDEX.md ] && ok "legacy: ledger indexes the legacy layout" \
  || bad "legacy: ledger missed the legacy records"
# once the default root exists it wins, and the warning stops
mkdir -p docs/engineering
run decide index
no "legacy"
[ -f docs/engineering/decisions/INDEX.md ] && ok "legacy: an existing docs/engineering/ takes over" \
  || bad "legacy: default root ignored once present"

# an unrelated specs/ directory is not mistaken for the legacy layout
newrepo "$TMP/unrelated"; mkdir -p specs; echo "# api tests" > specs/README.md
run plan_feature new thing --kind crud --tier small --work api
no "legacy"
[ -f docs/engineering/specs/thing/spec.md ] && ok "legacy: a specs/ dir without spec records is ignored" \
  || bad "legacy: an unrelated specs/ dir pinned the old layout"

# this plugin repo pins its own top-level layout with .100x.json {"root": "."}
cd "$ROOT"
run plan_feature audit specs/login
rc_is 0 $? "plugin repo: specs/login audits from the top-level layout"
no "legacy"

echo
echo "pipeline-e2e: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
