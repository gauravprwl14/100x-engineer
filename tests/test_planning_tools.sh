#!/usr/bin/env bash
# Regression suite for the planning layer: decide.py, plan_feature.py, design_drift.py.
# Asserts detection AND absence of false positives.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-54s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-54s\n' "$1"; [ -s /tmp/pt.out ] && sed 's/^/       /' /tmp/pt.out | head -6; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -q "$1" /tmp/pt.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -q "$1" /tmp/pt.out && bad "false positive: $1" || ok "no false positive: $1"; }

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
python3 "$ROOT/scripts/design_drift.py" "$TMP/specs/f/spec.md" "$TMP/src" >/tmp/pt.out 2>&1
rc_is 1 $? "drift: missing participant detected"
has "PaymentGateway"
no "OrderService"
no "(Client)"

cat > "$TMP/src/payment.gateway.ts" <<'TS'
export class PaymentGateway { async charge(amount: number) { return true; } }
TS
python3 "$ROOT/scripts/design_drift.py" "$TMP/specs/f/spec.md" "$TMP/src" >/tmp/pt.out 2>&1
rc_is 0 $? "drift: clears once implemented"

# a comment naming a symbol must NOT count as implementation
rm "$TMP/src/payment.gateway.ts"
printf '// TODO wire PaymentGateway and charge the amount\nexport const x = 1;\n' > "$TMP/src/note.ts"
python3 "$ROOT/scripts/design_drift.py" "$TMP/specs/f/spec.md" "$TMP/src" >/tmp/pt.out 2>&1
rc_is 1 $? "drift: a comment does not count as implementation"
has "PaymentGateway"
rm "$TMP/src/note.ts"

# ---------- plan_feature, in a CONSUMER repo ----------
# These tools must write into the user's project, not into the installed plugin.
CONS="$TMP/consumer"; mkdir -p "$CONS"; cd "$CONS"
git init -q; git config user.email e@e; git config user.name e
echo x > f.txt; git add -A; git commit -qm init

python3 "$ROOT/scripts/plan_feature.py" new thing --kind crud >/tmp/pt.out 2>&1
[ -f "$CONS/specs/thing/spec.md" ] && ok "plan: spec created in the consumer repo" \
  || bad "plan: spec not created in the consumer repo"
[ ! -d "$ROOT/specs/thing" ] && ok "plan: did NOT write into the plugin dir" \
  || bad "plan: leaked a spec into the plugin dir"

python3 "$ROOT/scripts/plan_feature.py" audit "$CONS/specs/thing" >/tmp/pt.out 2>&1
rc_is 1 $? "plan: fresh spec fails audit"
has "still TODO"
has "no recommendation"

python3 "$ROOT/scripts/plan_feature.py" new unknownkind --kind nosuchkind >/tmp/pt.out 2>&1
rc_is 2 $? "plan: unknown kind rejected"

# ---------- the plugin's own worked example ----------
cd "$ROOT"
python3 "$ROOT/scripts/plan_feature.py" audit "$ROOT/specs/login" >/tmp/pt.out 2>&1
rc_is 0 $? "plan: the completed worked spec passes audit"
grep -q "7 accepted as default" /tmp/pt.out && ok "plan: counts defaults correctly (pipe-escaping)" \
  || bad "plan: default count wrong"

# ---------- decide ----------
python3 "$ROOT/scripts/decide.py" index >/tmp/pt.out 2>&1
rc_is 0 $? "decide: index regenerates"
[ -f "$ROOT/decisions/INDEX.md" ] && ok "decide: INDEX.md exists" || bad "decide: no INDEX.md"
grep -qE "^\| \[ADR-0001\]" "$ROOT/decisions/INDEX.md" 2>/dev/null \
  && ok "decide: index table contains the ADR row" || bad "decide: ADR row missing"

python3 "$ROOT/scripts/decide.py" lint >/tmp/pt.out 2>&1
rc_is 0 $? "decide: the real ADR passes lint"

python3 "$ROOT/scripts/decide.py" verify >/tmp/pt.out 2>&1
grep -q "unverifiable" /tmp/pt.out && ok "decide: reports unverifiable assumptions" \
  || bad "decide: hides unverifiable assumptions"

python3 "$ROOT/scripts/decide.py" trace examples/login/src/auth.service.ts >/tmp/pt.out 2>&1
has "ADR-0001"
python3 "$ROOT/scripts/decide.py" trace src/nowhere/else.ts >/tmp/pt.out 2>&1
has "no recorded decision"

# a decision record that names a winner and nothing else must be rejected
mkdir -p "$CONS/decisions"
cat > "$CONS/decisions/ADR-0009-thin.md" <<'MD'
# ADR-0009: Use Postgres
```json meta
{"id":"ADR-0009","title":"Use Postgres","status":"accepted",
 "options":[{"name":"Postgres","chosen":true}],"assumptions":[]}
```
MD
cd "$CONS"
python3 "$ROOT/scripts/decide.py" lint >/tmp/pt.out 2>&1
rc_is 1 $? "decide: lint rejects a single-option record"
has "not a decision"
has "no assumptions recorded"
cd "$ROOT"

echo
echo "planning-tools: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
