#!/usr/bin/env bash
# Regression suite for craft_check.py. For every check: a planted violation AND
# a clean file that must NOT be flagged. The clean-file assertions are the
# important half -- a code-shape checker with false positives gets disabled.
# Run: bash tests/test_craft_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
CC="$ROOT/scripts/craft_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src
printf 'def add(a, b):\n    return a + b\n' > src/core.py
git add -A; git commit -qm init >/dev/null

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [--only X ...]
  local exp="$1" label="$2"; shift 2
  python3 "$CC" "$@" >/tmp/cc.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-56s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-56s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' /tmp/cc.out; fi
}
has() { grep -q -- "$1" /tmp/cc.out && { PASS=$((PASS+1)); printf '  ok   %-56s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "NOT reported: $1"; }; }
nothas() { grep -q -- "$1" /tmp/cc.out && { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "false positive: $1"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-56s\n' "no false positive: $1"; }; }
reset_diff() { git checkout -q -- . ; git clean -qfd . ; }

# =========================================================================
# function-length -- python (ast, exact) and TS (regex/brace heuristic)
# =========================================================================
python3 - <<'PYEOF'
lines = ["def big_function(x):"]
lines += [f"    x = x + {i}" for i in range(70)]
lines.append("    return x")
open("src/big.py", "w").write("\n".join(lines) + "\n")
PYEOF
expect 1 "function-length: long python function detected" --only function-length --strict
has "big_function.*72 lines"
reset_diff

printf 'def calculate_total(line_items):\n    total = 0\n    for item in line_items:\n        total += item.price\n    return total\n' > src/short.py
expect 0 "function-length: short python function is not flagged" --only function-length --strict
nothas "calculate_total"
reset_diff

python3 - <<'PYEOF'
lines = ["function bigFn(x) {"]
lines += [f"  x = x + {i};" for i in range(70)]
lines.append("  return x;")
lines.append("}")
open("src/big.ts", "w").write("\n".join(lines) + "\n")
PYEOF
expect 1 "function-length: long TS function detected" --only function-length --strict
has "bigFn.*73 lines"
reset_diff

printf 'export function add(a: number, b: number): number {\n  return a + b;\n}\n' > src/short.ts
expect 0 "function-length: short TS function is not flagged" --only function-length --strict
nothas "src/short.ts"
reset_diff

# =========================================================================
# param-count -- python and TS
# =========================================================================
printf 'def many_params(a, b, c, d, e, f, g):\n    return a\n' > src/params.py
expect 1 "param-count: 7-param python function detected" --only param-count --strict
has "many_params.*7 parameters"
reset_diff

printf 'def three_params(a, b, c):\n    return a + b + c\n' > src/params_ok.py
expect 0 "param-count: 3-param python function is not flagged" --only param-count --strict
nothas "three_params"
reset_diff

printf 'function manyParams(a, b, c, d, e, f, g) {\n  return a;\n}\n' > src/params.ts
expect 1 "param-count: 7-param TS function detected" --only param-count --strict
has "manyParams.*7 parameters"
reset_diff

printf 'function threeParams(a: number, b: number, c: number): number {\n  return a + b + c;\n}\n' > src/params_ok.ts
expect 0 "param-count: 3-param TS function is not flagged" --only param-count --strict
nothas "threeParams"
reset_diff

# =========================================================================
# nesting-depth -- python and TS
# =========================================================================
cat > src/deep.py <<'EOF'
def deep(x):
    if x:
        for i in range(3):
            while i:
                try:
                    if x > 1:
                        return i
                except Exception:
                    pass
    return x
EOF
expect 1 "nesting-depth: 5-deep python function detected" --only nesting-depth --strict
has "deep.*nests 5 levels"
reset_diff

cat > src/shallow.py <<'EOF'
def shallow(items):
    total = 0
    for item in items:
        if item.active:
            total += item.value
    return total
EOF
expect 0 "nesting-depth: shallow python function is not flagged" --only nesting-depth --strict
nothas "shallow.*nests"
reset_diff

cat > src/deep.ts <<'EOF'
function deepNest(x: number): number {
  if (x) {
    for (let i = 0; i < 3; i++) {
      while (i) {
        try {
          if (x > 1) {
            return i;
          }
        } catch (e) {}
      }
    }
  }
  return x;
}
EOF
expect 1 "nesting-depth: 5-deep TS function detected" --only nesting-depth --strict
has "deepNest.*nests 5 levels"
reset_diff

cat > src/shallow.ts <<'EOF'
function shallowFn(items: Item[]): number {
  let total = 0;
  for (const item of items) {
    if (item.active) {
      total += item.value;
    }
  }
  return total;
}
EOF
expect 0 "nesting-depth: shallow TS function is not flagged" --only nesting-depth --strict
nothas "shallowFn.*nests"
reset_diff

# =========================================================================
# boolean-flag-arg (advisory; test files are excluded by design)
# =========================================================================
cat > src/flag.py <<'EOF'
def save(record, publish):
    return record


def caller():
    return save(1, True)
EOF
expect 1 "boolean-flag-arg: positional literal detected" --only boolean-flag-arg --strict
has "save(\.\.\.)"
reset_diff

cat > src/flag_ok.py <<'EOF'
def save(record, publish=True):
    return record


def caller():
    return save(1, publish=True)
EOF
expect 0 "boolean-flag-arg: keyword arg is not flagged" --only boolean-flag-arg --strict
nothas "save(\.\.\.)"
reset_diff

# =========================================================================
# bare-except / bare-catch (BLOCKING -- exit 1 even without --strict)
# =========================================================================
cat > src/swallow.py <<'EOF'
def risky():
    try:
        do_thing()
    except Exception:
        pass
EOF
expect 1 "bare-except: swallowed python exception detected (blocking)" --only bare-except
has "swallows the error"
reset_diff

cat > src/handled.py <<'EOF'
def risky():
    try:
        do_thing()
    except ValueError as e:
        logger.error(e)
        raise
EOF
expect 0 "bare-except: log-then-raise is not flagged" --only bare-except
nothas "swallows the error"
reset_diff

cat > src/swallow.ts <<'EOF'
function risky(): void {
  try {
    doThing();
  } catch (e) {}
}
EOF
expect 1 "bare-except: swallowed TS exception detected (blocking)" --only bare-except
has "catch block swallows"
reset_diff

cat > src/handled.ts <<'EOF'
function risky(): void {
  try {
    doThing();
  } catch (e) {
    console.error("failed", e);
    throw e;
  }
}
EOF
expect 0 "bare-except: log-then-rethrow TS is not flagged" --only bare-except
nothas "catch block swallows"
reset_diff

# =========================================================================
# vague-names -- python and TS
# =========================================================================
cat > src/vague.py <<'EOF'
def process(data):
    manager = data
    return manager
EOF
expect 1 "vague-names: process/data/manager detected" --only vague-names --strict
has "named .process."
has "named .data."
has "named .manager."
reset_diff

cat > src/descriptive.py <<'EOF'
def calculate_discount(order, discount_percent):
    subtotal_cents = order.subtotal_cents
    return subtotal_cents * discount_percent // 100
EOF
expect 0 "vague-names: descriptive python names are not flagged" --only vague-names --strict
nothas "reveal intent"
reset_diff

cat > src/vague.ts <<'EOF'
function process(data: number): number {
  const helper = data;
  return helper;
}
EOF
expect 1 "vague-names: process/data/helper (TS) detected" --only vague-names --strict
has "named .process."
has "named .helper."
reset_diff

cat > src/descriptive.ts <<'EOF'
function calculateDiscount(orderTotalCents: number, discountPercent: number): number {
  return Math.floor((orderTotalCents * discountPercent) / 100);
}
EOF
expect 0 "vague-names: descriptive TS names are not flagged" --only vague-names --strict
nothas "reveal intent"
reset_diff

# =========================================================================
# money-as-float -- python and TS
# =========================================================================
printf 'def charge(amount: float):\n    return amount\n' > src/money.py
expect 1 "money-as-float: float-typed amount detected (python)" --only money-as-float --strict
has "amount.*typed .float."
reset_diff

printf 'def charge(amount_cents: int):\n    return amount_cents\n' > src/money_ok.py
expect 0 "money-as-float: int minor-unit is not flagged (python)" --only money-as-float --strict
nothas "money_ok.py"
reset_diff

printf 'function charge(amount: number): number {\n  return amount;\n}\n' > src/money.ts
expect 1 "money-as-float: number-typed amount detected (TS)" --only money-as-float --strict
has "amount.*typed .number."
reset_diff

printf 'function charge(amountCents: number): number {\n  return amountCents;\n}\n' > src/money_ok.ts
expect 0 "money-as-float: xCents (int minor-unit signal) is not flagged (TS)" --only money-as-float --strict
nothas "money_ok.ts"
reset_diff

# =========================================================================
# demeter-chain -- language-agnostic regex, tested once per language
# =========================================================================
printf 'def ship(order):\n    return order.customer.address.city.upper()\n' > src/demeter.py
expect 1 "demeter-chain: 4-deep chain detected (python)" --only demeter-chain --strict
has "reaches through 4 collaborators"
reset_diff

printf 'def ship(order):\n    return order.city\n' > src/demeter_ok.py
expect 0 "demeter-chain: single-hop access is not flagged" --only demeter-chain --strict
nothas "Law of Demeter"
reset_diff

printf 'function ship(order) {\n  return order.customer.address.city.toUpperCase();\n}\n' > src/demeter.ts
expect 1 "demeter-chain: 4-deep chain detected (TS)" --only demeter-chain --strict
has "reaches through 4 collaborators"
reset_diff

printf 'const path = require("path");\nfunction j(a, b) {\n  return path.join(a, b);\n}\n' > src/demeter_ok.ts
expect 0 "demeter-chain: 1-dot stdlib call is not flagged" --only demeter-chain --strict
nothas "Law of Demeter"
reset_diff

# =========================================================================
# diff-scoping: a pre-existing violation untouched by the diff is not re-flagged
# =========================================================================
python3 - <<'PYEOF'
lines = ["def legacy_vague(data):"]
lines += [f"    data = data + {i}" for i in range(70)]
lines.append("    return data")
open("src/legacy.py", "w").write("\n".join(lines) + "\n")
PYEOF
git add -A; git commit -qm "pre-existing violation, committed to baseline" >/dev/null
printf '\n\ndef unrelated_add(first_value, second_value):\n    return first_value + second_value\n' >> src/legacy.py
expect 0 "diff-scoping: untouched pre-existing violation is not re-flagged" --strict
nothas "legacy_vague"
git checkout -q -- src/legacy.py

echo
echo "craft_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
