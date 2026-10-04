#!/usr/bin/env bash
# Regression suite for the planning layer: decide.py, plan_feature.py, design_drift.py.
# Asserts detection AND absence of false positives.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-54s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-54s\n' "$1"; [ -s $OUT/pt.out ] && sed 's/^/       /' $OUT/pt.out | head -6; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -q "$1" $OUT/pt.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -q "$1" $OUT/pt.out && bad "false positive: $1" || ok "no false positive: $1"; }

# ---------- design_drift ----------
mkdir -p "$TMP/specs/f" "$TMP/src"
cat > "$TMP/specs/f/spec.md" <<'MD'
# f
```mermaid
sequenceDiagram
  %% external: C
  actor U as User
  participant C as Client
  participant A as OrderController
  participant S as OrderService
  participant P as PaymentGateway
  U->>C: click pay
  C->>A: POST /orders
  A->>S: placeOrder(dto)
  S->>P: charge(amount)
MD
printf '```\n' >> "$TMP/specs/f/spec.md"
cat > "$TMP/src/order.controller.ts" <<'TS'
export class OrderController { async post(dto) { return this.svc.placeOrder(dto); } }
TS
cat > "$TMP/src/order.service.ts" <<'TS'
export class OrderService { async placeOrder(dto) { return 1; } }
TS
python3 "$ROOT/scripts/design_drift.py" "$TMP/specs/f/spec.md" "$TMP/src" >$OUT/pt.out 2>&1
rc_is 1 $? "drift: missing participant detected"
has "PaymentGateway"
no "OrderService"
no "(Client)"

cat > "$TMP/src/payment.gateway.ts" <<'TS'
export class PaymentGateway { async charge(amount: number) { return true; } }
TS
python3 "$ROOT/scripts/design_drift.py" "$TMP/specs/f/spec.md" "$TMP/src" >$OUT/pt.out 2>&1
rc_is 0 $? "drift: clears once implemented"

# a comment naming a symbol must NOT count as implementation
rm "$TMP/src/payment.gateway.ts"
printf '// TODO wire PaymentGateway and charge the amount\nexport const x = 1;\n' > "$TMP/src/note.ts"
python3 "$ROOT/scripts/design_drift.py" "$TMP/specs/f/spec.md" "$TMP/src" >$OUT/pt.out 2>&1
rc_is 1 $? "drift: a comment does not count as implementation"
has "PaymentGateway"
rm "$TMP/src/note.ts"

# ---------- plan_feature, in a CONSUMER repo ----------
# These tools must write into the user's project, not into the installed plugin.
CONS="$TMP/consumer"; mkdir -p "$CONS"; cd "$CONS"
git init -q; git config user.email e@e; git config user.name e
echo x > f.txt; git add -A; git commit -qm init

python3 "$ROOT/scripts/plan_feature.py" new notier --kind crud --work api >$OUT/pt.out 2>&1
rc_is 2 $? "plan: new without --tier is refused"
has "tier is required: one of"
[ ! -d "$CONS/docs/engineering/specs/notier" ] && ok "plan: nothing written without a tier" || bad "plan: wrote a spec with no tier"

python3 "$ROOT/scripts/plan_feature.py" new thing --kind crud --tier small --work api >$OUT/pt.out 2>&1
[ -f "$CONS/docs/engineering/specs/thing/spec.md" ] && ok "plan: spec created in the consumer repo" \
  || bad "plan: spec not created in the consumer repo"
[ ! -d "$ROOT/specs/thing" ] && ok "plan: did NOT write into the plugin dir" \
  || bad "plan: leaked a spec into the plugin dir"

python3 "$ROOT/scripts/plan_feature.py" audit "$CONS/docs/engineering/specs/thing" >$OUT/pt.out 2>&1
rc_is 1 $? "plan: fresh spec fails audit"
has "still TODO"
has "no recommendation"

has "still contain a template placeholder"
has "§0b implicit requirement(s) still TODO"
grep -q "^## 2b. Acceptance criteria" "$CONS/docs/engineering/specs/thing/spec.md" \
  && grep -q "^AC-1: <!-- observable outcome --> (R1, S1)" "$CONS/docs/engineering/specs/thing/spec.md" \
  && ok "plan: new spec scaffolds the acceptance-criteria section" || bad "plan: no AC section scaffolded"
grep -q "^| # | check | command | gate | covers |" "$CONS/docs/engineering/specs/thing/spec.md" \
  && ok "plan: verification plan has a covers column" || bad "plan: no covers column"
[ ! -e "$CONS/specs" ] && ok "plan: nothing written at the repo top level" || bad "plan: wrote specs/ at the top level"

python3 "$ROOT/scripts/plan_feature.py" new unknownkind --kind nosuchkind --tier small >$OUT/pt.out 2>&1
rc_is 2 $? "plan: unknown kind rejected"
python3 "$ROOT/scripts/plan_feature.py" new badwork --kind crud --tier small --work desktop >$OUT/pt.out 2>&1
rc_is 2 $? "plan: unknown work type rejected"

# risk floor: auth implies elevated even when --risk none is passed
python3 "$ROOT/scripts/plan_feature.py" new authy --kind auth --tier small --work api --risk none >$OUT/pt.out 2>&1
has "risk: elevated (raised from none"
grep -q "^| risk | elevated |" "$CONS/docs/engineering/specs/authy/spec.md" && ok "plan: raised risk written to §0" \
  || bad "plan: raised risk not written to §0"
grep -q "^| all.pii-out-of-logs |" "$CONS/docs/engineering/specs/authy/spec.md" && ok "plan: elevated risk seeds PII row" \
  || bad "plan: elevated risk did not seed PII row"

# regulated small app: compliance rows yes, capacity rows no
python3 "$ROOT/scripts/plan_feature.py" new reg --kind crud --tier small --work api,iac --risk regulated >$OUT/pt.out 2>&1
grep -q "^| all.audit-trail |" "$CONS/docs/engineering/specs/reg/spec.md" && ok "plan: regulated seeds audit trail" \
  || bad "plan: regulated did not seed audit trail"
grep -qE "^\| iac\.multi-(region|az) \|" "$CONS/docs/engineering/specs/reg/spec.md" \
  && bad "plan: regulated small app forced into multi-AZ/region" || ok "plan: regulated small app has no multi-AZ/region"

# public-api alias pre-answers the audience question
python3 "$ROOT/scripts/plan_feature.py" new pub --kind crud --tier prototype --work public-api >$OUT/pt.out 2>&1
grep -q "^| ask.api-audience | .* | ASK(public" "$CONS/docs/engineering/specs/pub/spec.md" && ok "plan: public-api answers ask.api-audience" \
  || bad "plan: public-api did not answer ask.api-audience"

# ---------- audit rules, one defect at a time from the passing worked spec ----------
swap() {
  python3 - "$1" "$2" "$3" <<'PY2'
import sys, pathlib
f, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(f); t = p.read_text()
if old not in t:
    print(f"TEST BUG: pattern not found: {old!r}", file=sys.stderr); sys.exit(1)
p.write_text(t.replace(old, new, 1))
PY2
}
W="$CONS/docs/engineering/specs/w"; mkdir -p "$W"
# the worked spec's header links its PRD at examples/login (relative to the git root)
mkdir -p "$CONS/examples/login"; cp "$ROOT/examples/login/prd.md" "$CONS/examples/login/prd.md"
fresh() { cp "$ROOT/specs/login/spec.md" "$W/spec.md"; }
audit_w() { python3 "$ROOT/scripts/plan_feature.py" audit "$W" >$OUT/pt.out 2>&1; }

fresh; audit_w; rc_is 0 $? "audit: copy of the worked spec passes"

fresh; swap "$W/spec.md" "| n/a(no new process — the existing service keeps its probes and shutdown hook) |" "| n/a |"
audit_w; rc_is 1 $? "audit: bare n/a without a reason rejected"
has "outside the allowlist"

fresh; swap "$W/spec.md" "| n/a(no new process — the existing service keeps its probes and shutdown hook) |" "| done-ish |"
audit_w; rc_is 1 $? "audit: status outside the allowlist rejected"
has "api.health-graceful-shutdown"

fresh; swap "$W/spec.md" "A returning user signs in" "<!-- outcome --> A returning user signs in"
audit_w; rc_is 1 $? "audit: placeholder in prose (not a table) rejected"
has "template placeholder"

fresh; swap "$W/spec.md" "| scale tier | small |" "| scale tier | |"
audit_w; rc_is 1 $? "audit: missing tier rejected"
has "scale tier"

fresh; swap "$W/spec.md" "## 0. Non-functional requirements" "## Zero"
audit_w; rc_is 1 $? "audit: missing §0 section rejected"
has "load tier must be"

fresh; swap "$W/spec.md" "| risk | elevated |" "| risk | none |"
audit_w; rc_is 1 $? "audit: risk below the auth floor rejected"
has "below the floor"

fresh; swap "$W/spec.md" "| ASK(single region: the existing Postgres and Redis region — PRD §4, source user) |" "| ASK |"
audit_w; rc_is 1 $? "audit: unanswered residency rejected"
has "unanswered"

fresh; swap "$W/spec.md" "| ASK(single region: the existing Postgres and Redis region — PRD §4, source user) |" "| ASSUMED(single region) |"
audit_w; rc_is 1 $? "audit: ASSUMED residency blocks ready"
has "ask.data-residency"

fresh; swap "$W/spec.md" "| ASK(none — PRD §4, source user) |" "| ASSUMED(none) |"
audit_w; rc_is 1 $? "audit: ASSUMED compliance regime blocks ready"
has "ask.compliance-regime"

fresh; grep -q "| ASSUMED(sessions are disposable" "$W/spec.md" && audit_w
rc_is 0 $? "audit: ASSUMED accepted for a non-blocking C item (rpo-rto)"

fresh; swap "$W/spec.md" "| ASSUMED(sessions are disposable — losing them signs users out; users table follows the existing Postgres backup policy) |" "| accepted |"
audit_w; rc_is 1 $? "audit: a C item cannot be silently accepted"
has "is class C"

fresh; swap "$W/spec.md" "| covered | E6 \`session.guard.spec.ts\`" "| waived(no time) | E6 \`session.guard.spec.ts\`"
audit_w; rc_is 1 $? "audit: waiving a non-waivable item rejected"
has "non-waivable"

fresh; swap "$W/spec.md" "| covered | E24 \`log-redaction.spec.ts\` |" "| covered | — |"
audit_w; rc_is 1 $? "audit: covered baseline row with no evidence rejected"
has "no evidence"

fresh; grep -v "^| api.ssrf-guard |" "$W/spec.md" > "$W/s2" && mv "$W/s2" "$W/spec.md"
audit_w; rc_is 1 $? "audit: missing applicable baseline row rejected"
has "missing from §0b"

fresh; swap "$W/spec.md" "| Q1 | default |" "| Q1 | maybe |"
audit_w; rc_is 1 $? "audit: untyped question rejected"
has "not tagged must-ask|default"

fresh; swap "$W/spec.md" "None of these block implementation" \
"| Q4 | default | a | b | c | no |
| Q5 | default | a | b | c | no |
| Q6 | default | a | b | c | no |

None of these block implementation"
python3 - "$W/spec.md" <<'PY2'
import sys,pathlib
p=pathlib.Path(sys.argv[1]); t=p.read_text()
t=t.replace("| no |\n\n| Q4","| no |\n| Q4")
p.write_text(t)
PY2
audit_w; rc_is 1 $? "audit: more than five questions rejected"
has "at most 5"

fresh; python3 - "$W/spec.md" <<'PY2'
import sys,pathlib,re
p=pathlib.Path(sys.argv[1]); t=p.read_text()
t=re.sub(r"(## 14\. Cost\n).*", r"\1\n", t, flags=re.S)
p.write_text(t)
PY2
audit_w; rc_is 1 $? "audit: blank design-doc section rejected"
has "'## 14. Cost' is blank"

fresh; python3 - "$W/spec.md" <<'PY2'
import sys,pathlib,re
p=pathlib.Path(sys.argv[1]); t=p.read_text()
t=re.sub(r"(## 14\. Cost\n).*", r"\1\nN/A\n", t, flags=re.S)
p.write_text(t)
PY2
audit_w; rc_is 1 $? "audit: bare N/A section rejected"
has "'## 14. Cost' is blank"

fresh; swap "$W/spec.md" "## 11. Privacy" "## 11. Notes"
audit_w; rc_is 1 $? "audit: missing design-doc section rejected"
has "missing section '## 11. Privacy'"

# ---------- acceptance criteria: the join key PRD -> AC -> plan.json -> test ----------
fresh; python3 - "$W/spec.md" <<'PY2'
import sys,pathlib,re
p=pathlib.Path(sys.argv[1]); t=p.read_text()
t=re.sub(r"## 2b\. Acceptance criteria\n.*?(?=\n## 3\.)", "", t, flags=re.S)
p.write_text(t)
PY2
audit_w; rc_is 1 $? "audit: missing acceptance-criteria section rejected"
has "no '## 2b. Acceptance criteria' section"

fresh; python3 - "$W/spec.md" <<'PY2'
import sys,pathlib,re
p=pathlib.Path(sys.argv[1]); t=p.read_text()
t=re.sub(r"^AC-\d+: .*\n", "", t, flags=re.M)
p.write_text(t)
PY2
audit_w; rc_is 1 $? "audit: section with zero ACs rejected"
has "§2b has no acceptance criteria"

fresh; swap "$W/spec.md" "AC-2: A wrong password" "AC-1: A wrong password"
audit_w; rc_is 1 $? "audit: duplicate AC id rejected"
has "defined more than once: AC-1"

fresh; swap "$W/spec.md" "AC-6: A user can sign in with Google through OAuth, and a callback with a replayed \`state\` or a missing PKCE verifier is rejected. (R5, S5)" "AC-6: OAuth works. (R5, S5)"
audit_w; rc_is 1 $? "audit: AC with no observable outcome rejected"
has "no observable outcome (first: AC-6)"

fresh; swap "$W/spec.md" "is rejected. (R5, S5)" "is rejected. (R5)"
audit_w; rc_is 1 $? "audit: in-scope item with no AC rejected"
has "in-scope item(s) with no acceptance criterion: S5"

fresh; swap "$W/spec.md" "lifts after 15 minutes. (R4, S4)" "lifts after 15 minutes. (S4)"
audit_w; rc_is 1 $? "audit: AC without a requirement link rejected when a PRD exists"
has "no PRD requirement link (first: AC-5)"

fresh; swap "$W/spec.md" "lifts after 15 minutes. (R4, S4)" "lifts after 15 minutes. (R9, S4)"
audit_w; rc_is 1 $? "audit: AC linking a requirement the PRD lacks rejected"
has "link requirement(s) not in examples/login/prd.md: R9"

fresh; swap "$W/spec.md" "| prd | examples/login |" "| prd | none |"
swap "$W/spec.md" "lifts after 15 minutes. (R4, S4)" "lifts after 15 minutes. (S4)"
audit_w; rc_is 0 $? "audit: no PRD -> requirement links are not required (no false positive)"
grep -q "no PRD was found" $OUT/pt.out && ok "audit: warns that R links are unchecked without a PRD" \
  || bad "audit: silent about unchecked R links"

fresh; swap "$W/spec.md" "| pre-PR | AC-1, AC-2, AC-3, AC-4, AC-5 |" "| pre-PR | AC-1, AC-2, AC-3, AC-4 |"
swap "$W/spec.md" "| AC-1, AC-2, AC-3, AC-4, AC-5, AC-6 |" "| AC-1, AC-2, AC-3, AC-4, AC-6 |"
audit_w; rc_is 1 $? "audit: AC no verification row covers rejected"
has "no verification row covers: AC-5"

fresh; swap "$W/spec.md" "| pre-commit | AC-2, AC-6 |" "| pre-commit | AC-2, AC-6, AC-9 |"
audit_w; rc_is 1 $? "audit: verification row covering an undefined AC rejected"
has "covers undefined criteria: AC-9"

fresh; swap "$W/spec.md" "AC-3: Logout" "- **AC-3** Logout"
audit_w; rc_is 1 $? "audit: non-canonical AC shape in §2b rejected"
has "write it as \`AC-3: <observable outcome>"

# ---------- the plugin's own worked example ----------
cd "$ROOT"
python3 "$ROOT/scripts/plan_feature.py" audit "$ROOT/specs/login" >$OUT/pt.out 2>&1
rc_is 0 $? "plan: the completed worked spec passes audit"
grep -q "7 accepted as default" $OUT/pt.out && ok "plan: counts defaults correctly (pipe-escaping)" \
  || bad "plan: default count wrong"

# ---------- decide ----------
python3 "$ROOT/scripts/decide.py" index >$OUT/pt.out 2>&1
rc_is 0 $? "decide: index regenerates"
[ -f "$ROOT/decisions/INDEX.md" ] && ok "decide: INDEX.md exists" || bad "decide: no INDEX.md"
grep -qE "^\| \[ADR-0001\]" "$ROOT/decisions/INDEX.md" 2>/dev/null \
  && ok "decide: index table contains the ADR row" || bad "decide: ADR row missing"

python3 "$ROOT/scripts/decide.py" lint >$OUT/pt.out 2>&1
rc_is 0 $? "decide: the real ADR passes lint"

python3 "$ROOT/scripts/decide.py" verify >$OUT/pt.out 2>&1
grep -q "unverifiable" $OUT/pt.out && ok "decide: reports unverifiable assumptions" \
  || bad "decide: hides unverifiable assumptions"

python3 "$ROOT/scripts/decide.py" trace examples/login/src/auth.service.ts >$OUT/pt.out 2>&1
has "ADR-0001"
python3 "$ROOT/scripts/decide.py" trace src/nowhere/else.ts >$OUT/pt.out 2>&1
has "no recorded decision"

# a decision record that names a winner and nothing else must be rejected
mkdir -p "$CONS/docs/engineering/decisions"
cat > "$CONS/docs/engineering/decisions/ADR-0009-thin.md" <<'MD'
# ADR-0009: Use Postgres
```json meta
{"id":"ADR-0009","title":"Use Postgres","status":"accepted",
 "options":[{"name":"Postgres","chosen":true}],"assumptions":[]}
```
MD
cd "$CONS"
python3 "$ROOT/scripts/decide.py" lint >$OUT/pt.out 2>&1
rc_is 1 $? "decide: lint rejects a single-option record"
has "not a decision"
has "no assumptions recorded"
rm -f "$CONS/docs/engineering/decisions/ADR-0009-thin.md"

# fit is a pass/fail filter applied before any weighted comparison (same rule as prd.py)
adr() { # adr <options-json> [extra top-level json]
  printf '# ADR-0010: Queue\n```json meta\n{"id":"ADR-0010","title":"Queue","status":"accepted","options":%s,"assumptions":[{"id":"A1","claim":"c","verify":"true","revisit_when":"w"}]%s}\n```\n' \
    "$1" "${2:-}" > "$CONS/docs/engineering/decisions/ADR-0010-queue.md"
  python3 "$ROOT/scripts/decide.py" lint >$OUT/pt.out 2>&1
}
SC='"scores":{"reversibility":%s,"blast radius":%s,"moving parts":%s,"already-in-use":%s,"exit cost":%s}'
sc() { printf "$SC" "$@"; }
adr '[{"name":"SQS","fit":"pass","chosen":true,"why":"managed"},{"name":"cron","fit":"fail","chosen":false,"why_not":"misses the 1s latency need"}]'
rc_is 0 $? "decide: fit-passing chosen option passes lint (no false positive)"
adr '[{"name":"SQS","chosen":true,"why":"managed"},{"name":"cron","chosen":false,"why_not":"slow"}]'
rc_is 1 $? "decide: options without fit rejected"
has "set \"fit\": \"pass\" or \"fail\""
adr '[{"name":"SQS","fit":"fail","chosen":true,"why":"managed"},{"name":"cron","fit":"pass","chosen":false,"why_not":"slow"}]'
rc_is 1 $? "decide: a chosen option that fails fit rejected"
has "fails the fit filter"
adr '[{"name":"SQS","fit":"fail","chosen":true,"why":"managed"},{"name":"cron","fit":"fail","chosen":false,"why_not":"slow"}]'
rc_is 1 $? "decide: no fit-passing option rejected"
has "no option passes the fit filter"
adr "[{\"name\":\"SQS\",\"fit\":\"pass\",\"chosen\":true,\"why\":\"managed\",$(sc 2 2 2 2 2)},{\"name\":\"Kafka\",\"fit\":\"pass\",\"chosen\":false,\"why_not\":\"ops\",$(sc 5 5 5 5 5)}]"
rc_is 1 $? "decide: chosen below the top fit-passing score without override rejected"
has "is not the top fit-passing score"
adr "[{\"name\":\"SQS\",\"fit\":\"pass\",\"chosen\":true,\"why\":\"managed\",$(sc 2 2 2 2 2)},{\"name\":\"Kafka\",\"fit\":\"pass\",\"chosen\":false,\"why_not\":\"ops\",$(sc 5 5 5 5 5)}]" ',"override_reason":"team already runs SQS"'
rc_is 0 $? "decide: an override_reason allows a lower score"
adr "[{\"name\":\"SQS\",\"fit\":\"pass\",\"chosen\":true,\"why\":\"managed\",$(sc 2 2 2 2 2)},{\"name\":\"Kafka\",\"fit\":\"fail\",\"chosen\":false,\"why_not\":\"ops\",$(sc 5 5 5 5 5)}]"
rc_is 0 $? "decide: a higher score that FAILS fit does not outrank the chosen option"
adr "[{\"name\":\"SQS\",\"fit\":\"pass\",\"chosen\":true,\"why\":\"managed\",$(sc 2 2 9 2 2)},{\"name\":\"cron\",\"fit\":\"fail\",\"chosen\":false,\"why_not\":\"slow\"}]"
rc_is 1 $? "decide: a score outside 1-5 rejected"
has "integer 1-5"
adr "[{\"name\":\"SQS\",\"fit\":\"pass\",\"chosen\":true,\"why\":\"managed\"},{\"name\":\"Kafka\",\"fit\":\"pass\",\"chosen\":false,\"why_not\":\"ops\",$(sc 5 5 5 5 5)},{\"name\":\"NATS\",\"fit\":\"pass\",\"chosen\":false,\"why_not\":\"new\",$(sc 4 4 4 4 4)}]"
rc_is 1 $? "decide: an unscored chosen option among scored alternatives rejected"
has "has no scores while 2 fit-passing options are scored"
adr "[{\"name\":\"SQS\",\"fit\":\"pass\",\"chosen\":true,\"why\":\"managed\",$(sc 5 5 5 5 5)},{\"name\":\"Kafka\",\"fit\":\"pass\",\"chosen\":false,\"why_not\":\"ops\",$(sc 2 2 2 2 2)},{\"name\":\"NATS\",\"fit\":\"pass\",\"chosen\":false,\"why_not\":\"new\",$(sc 4 4 4 4 4)}]"
rc_is 0 $? "decide: a scored top choice among scored alternatives passes"
no "has no scores"
adr "[{\"name\":\"SQS\",\"fit\":\"pass\",\"chosen\":true,\"why\":\"managed\"},{\"name\":\"Kafka\",\"fit\":\"pass\",\"chosen\":false,\"why_not\":\"ops\",$(sc 5 5 5 5 5)}]"
rc_is 0 $? "decide: one scored alternative does not force a score on the choice"
adr "[{\"name\":\"Queue\",\"fit\":\"pass\",\"chosen\":true,\"why\":\"managed\",$(sc 2 2 2 2 2)},{\"name\":\"Queue\",\"fit\":\"pass\",\"chosen\":false,\"why_not\":\"ops\",$(sc 5 5 5 5 5)}]"
rc_is 1 $? "decide: duplicate option names do not hide a higher score"
has "is not the top fit-passing score"
adr '["SQS",{"name":"cron","fit":"pass","chosen":true,"why":"simple"}]'
rc_is 1 $? "decide: a non-object option is a lint error"
has "option #1 is str"
no "Traceback"
python3 "$ROOT/scripts/decide.py" index >$OUT/pt.out 2>&1
no "Traceback"
adr '"SQS"'
rc_is 1 $? "decide: options that are not a list are a lint error"
has "options must be a list"
no "Traceback"
rm -f "$CONS/docs/engineering/decisions/ADR-0010-queue.md"
python3 -c "import sys; sys.path.insert(0, '$ROOT/scripts'); import decide, prd; sys.exit(0 if prd.WEIGHTS is decide.WEIGHTS else 1)" >/dev/null 2>&1
rc_is 0 $? "decide and prd score with one shared weight table"
cd "$ROOT"

# ---------- review_scope ----------
cd "$CONS"
mkdir -p src
cat > src/orders.ts <<'TS'
export interface OrderSink { send(o: unknown): void; }
export async function getInvoice(id: string) {
  return db.invoices.findOne(id);
}
export async function register(email: string) {
  if (await db.users.findOne(email)) throw new Error('taken');
  return db.users.insert(email);
}
TS
python3 "$ROOT/scripts/review_scope.py" >$OUT/pt.out 2>&1
rc_is 0 $? "review_scope: runs on a diff"
has "R1"
has "R6"
has "R7"
grep -q "src/orders.ts" $OUT/pt.out && ok "review_scope: attributes the question to the file" \
  || bad "review_scope: file attribution missing"

# non-code and fixture files must not be attributed to code questions
printf '# notes\n' > README_EXTRA.md
python3 "$ROOT/scripts/review_scope.py" >$OUT/pt.out 2>&1
grep -q "README_EXTRA.md" $OUT/pt.out && bad "review_scope: attributed a markdown file to a code question" \
  || ok "review_scope: excludes non-code files"
rm -f README_EXTRA.md

# a clean repo with no changes must say so
git add -A >/dev/null 2>&1; git commit -qm x >/dev/null 2>&1
python3 "$ROOT/scripts/review_scope.py" >$OUT/pt.out 2>&1
grep -q "no changes to review" $OUT/pt.out && ok "review_scope: quiet with no changes" \
  || bad "review_scope: noisy with no changes"
cd "$ROOT"

echo
echo "planning-tools: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
