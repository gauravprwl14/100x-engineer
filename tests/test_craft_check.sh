#!/usr/bin/env bash
# Regression suite for craft_check.py. For every check: a planted violation AND
# a clean file that must NOT be flagged. The clean-file assertions are the
# important half -- a code-shape checker with false positives gets disabled.
# Run: bash tests/test_craft_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
CC="$ROOT/scripts/craft_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src
printf 'def add(a, b):\n    return a + b\n' > src/core.py
git add -A; git commit -qm init >/dev/null

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [--only X ...]
  local exp="$1" label="$2"; shift 2
  python3 "$CC" "$@" >$OUT/cc.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-56s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-56s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' $OUT/cc.out; fi
}
has() { grep -q -- "$1" $OUT/cc.out && { PASS=$((PASS+1)); printf '  ok   %-56s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "NOT reported: $1"; }; }
nothas() { grep -q -- "$1" $OUT/cc.out && { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "false positive: $1"; } \
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

cat > src/hook.py <<'EOF'
def main():
    try:
        run()
    except Exception:  # fail-open: a hook must never block the session
        pass
    try:
        run()
    except Exception:
        pass  # fail-open: telemetry is best effort
EOF
cat > src/hook.ts <<'EOF'
function main(): void {
  try {
    run();
  } catch (e) {} // fail-open: analytics must not break checkout
}
EOF
expect 0 "bare-except: '# fail-open: <reason>' waiver honoured (py + ts)" --only bare-except
nothas "swallows the error"
reset_diff

cat > src/hook.py <<'EOF'
def main():
    try:
        run()
    except Exception:  # fail-open:
        pass
    try:
        run()
    except Exception:  # fail open, see docstring
        pass
EOF
expect 1 "bare-except: waiver without a reason, or misspelt, still flagged" --only bare-except
has "src/hook.py:4:"
has "src/hook.py:8:"
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
# short-names -- a 1-2 char name whose scope spans more than 5 lines
# =========================================================================
cat > src/short.py <<'EOF'
def summarize(orders):
    rs = []
    for order in orders:
        rs.append(order.total_cents)
    log_count(len(orders))
    log_count(len(orders))
    log_count(len(orders))
    return rs
EOF
cat > src/short.ts <<'EOF'
function summarize(orders: Order[]): number[] {
  const rs: number[] = [];
  for (const order of orders) {
    rs.push(order.totalCents);
  }
  logCount(orders.length);
  logCount(orders.length);
  return rs;
}
EOF
expect 1 "short-names: 2-char names over a long scope detected (py + TS)" --only short-names --strict
has "src/short.py:2: .rs. is 2 char"
has "src/short.ts:2: .rs. is 2 char"
reset_diff

mkdir -p tests
cat > src/short_ok.py <<'EOF'
def add(a, b):
    return a + b


def total_by_customer(rows, fn):
    totals = {}
    for i, row in enumerate(rows):
        for k, v in row.items():
            totals[k] = totals.get(k, 0) + v + i
    try:
        fn(totals)
    except ValueError as e:
        raise RuntimeError(totals) from e
    squares = [x * x for x in totals.values()]
    return totals, squares, fn, e
EOF
cat > tests/test_short_ok.py <<'EOF'
def test_totals_are_summed():
    t = build_table()
    t.add(1)
    t.add(2)
    t.add(3)
    t.add(4)
    assert t.total() == 10
EOF
cat > src/short_ok.ts <<'EOF'
export function sumRows(rows: number[][]): number {
  let total = 0;
  for (let i = 0; i < rows.length; i++) {
    for (const x of rows[i]) {
      total += x;
    }
    total += i;
  }
  return total;
}
EOF
expect 0 "short-names: loop indexes, e, fn, t-in-tests, short spans are not flagged" --only short-names --strict
nothas "char(s) but lives"
reset_diff

# =========================================================================
# abbreviations -- tmp/cfg/usr/mgr/calc/proc/cnt/idx/btn/arr, str/num/obj as names
# =========================================================================
cat > src/abbrev.py <<'EOF'
def calc_total(usr_cnt):
    cfg = load_settings()
    str = cfg.name
    return usr_cnt, str
EOF
cat > src/abbrev.ts <<'EOF'
export class Billing {
  procInvoice(invoice: Invoice): void {
    const tmpArr = [invoice];
    send(tmpArr);
  }
}
EOF
expect 1 "abbreviations: calc/usr/cfg/str (py) and proc/tmp (TS method + const) detected" --only abbreviations --strict
has "function .calc_total. abbreviates"
has "parameter .usr_cnt. abbreviates"
has "variable .cfg. abbreviates"
has "variable .str. abbreviates"
has "method .procInvoice. abbreviates"
has "declaration .tmpArr. abbreviates"
reset_diff

mkdir -p src/components
cat > src/abbrev_ok.py <<'EOF'
def process_order(order, strategy, counter):
    calculated_total = 0
    for idx, line in enumerate(order.lines):
        calculated_total += line.price_cents * idx
    cfg = strategy.settings
    return calculated_total, counter, cfg
EOF
cat > src/components/SubmitBar.tsx <<'EOF'
export function SubmitBar(props: SubmitBarProps) {
  const submitBtn = useRef(null);
  return <button ref={submitBtn}>{props.label}</button>;
}
EOF
printf '{"root": ".", "craft_allow_names": ["cfg"]}\n' > .100x.json
expect 0 "abbreviations: whole words, idx loop index, btn in a UI file, craft_allow_names" --only abbreviations --strict
nothas "abbreviates"
reset_diff

# =========================================================================
# boolean-predicate -- a boolean that does not read as a question
# =========================================================================
cat > src/flags.py <<'EOF'
def sync(items):
    active = True
    enabled: bool = False
    return active, enabled, items
EOF
cat > src/flags.ts <<'EOF'
export function sync(items: Item[]): boolean {
  let loaded = false;
  const visible: boolean = items.length > 0;
  return loaded && visible;
}
EOF
expect 1 "boolean-predicate: active/enabled (py) and loaded/visible (TS) detected" --only boolean-predicate --strict
has "boolean .active. does not read"
has "boolean .enabled. does not read"
has "boolean .loaded. does not read"
has "boolean .visible. does not read"
reset_diff

cat > src/flags_ok.py <<'EOF'
DEBUG = False


def sync(items):
    is_active = True
    has_items: bool = bool(items)
    ok = True
    should_retry = len(items) > 0
    return is_active, has_items, ok, should_retry, DEBUG
EOF
cat > src/flags_ok.ts <<'EOF'
const FEATURE_ON = false;
export function sync(items: Item[]): boolean {
  let isLoaded = false;
  const hasMore: boolean = items.length > 0;
  const canRetry = items.length > 0;
  return isLoaded && hasMore && canRetry && FEATURE_ON;
}
EOF
cat > src/models_ok.py <<'EOF'
from dataclasses import dataclass


@dataclass
class Task:
    title: str
    done: bool = False
    archived: bool


class Settings(BaseModel):
    enabled = True
EOF
cat > src/models_ok.ts <<'EOF'
export interface Task {
  done: boolean;
  archived?: boolean;
}
export type Flags = { enabled: boolean };
EOF
expect 0 "boolean-predicate: is_/has_ names, constants, ok, class fields not flagged" --only boolean-predicate --strict
nothas "does not read as a predicate"
reset_diff

# =========================================================================
# function-verb -- function and method names start with a verb
# =========================================================================
cat > src/verbs.py <<'EOF'
def total(user):
    return user.total


def median(values):
    ordered = sorted(values)
    return ordered[len(values) // 2]


def refund(payment):
    return payment.reverse()


def changed_files(base):
    return base.files


class Report:
    def order_summary(self, orders):
        lines = []
        for order in orders:
            lines.append(order.id)
            lines.append(order.status)
            lines.append(order.amount)
            lines.append(order.customer)
            lines.append(order.region)
            lines.append(order.channel)
            lines.append(order.created_at)
        return lines
EOF
cat > src/verbs.ts <<'EOF'
export function total(user: User): number {
  return user.total;
}
export function pendingOrders(orders: Order[]): Order[] {
  return orders.filter((order) => order.pending);
}
export class Invoice {
  amount(rate: number, lines: Line[]): number {
    let sum = 0;
    for (const line of lines) {
      sum += line.net;
      sum += line.tax;
      sum += line.fee;
      sum += line.shipping;
      sum -= line.discount;
    }
    sum = sum * rate;
    return sum;
  }
}
EOF
expect 1 "function-verb: long noun-named functions and methods detected (py + TS)" --only function-verb --strict
has "function .order_summary. does not start with a verb"
has "method .amount. does not start with a verb"
nothas "function .total."
nothas "function .median."
nothas "function .refund."
nothas "changed_files"
nothas "pendingOrders"
reset_diff

mkdir -p tests src/components
cat > src/verbs_ok.py <<'EOF'
import pytest


class Cart:
    def __init__(self, lines):
        self.lines = lines

    def __len__(self):
        return len(self.lines)

    @property
    def subtotal_cents(self):
        return sum(self.lines)

    def get_line(self, position):
        return self.lines[position]


def main():
    return build_cart()


@pytest.fixture
def empty_cart():
    return Cart([])
EOF
cat > tests/test_cart.py <<'EOF'
def cart_with_two_lines():
    return [1, 2]


def test_subtotal_adds_lines():
    assert sum(cart_with_two_lines()) == 3
EOF
cat > src/components/OrderSummary.tsx <<'EOF'
export function OrderSummary(props: OrderSummaryProps) {
  const handleClick = () => props.onSelect(props.order);
  return <button onClick={handleClick}>{props.order.label}</button>;
}
export function useOrders(customerId: string) {
  return useQuery(customerId);
}
EOF
cat > src/cart.ts <<'EOF'
export class Cart {
  constructor(private lines: number[]) {
    this.lines = lines;
  }
  get total() {
    return this.lines.length;
  }
  calculateTotal(): number {
    return this.lines.length;
  }
}
EOF
expect 0 "function-verb: dunders, property, main, fixture, tests, components, hooks, getters" --only function-verb --strict
nothas "does not start with a verb"
reset_diff

# A docstring does not count toward the noun-name limit: documenting a short function
# must never be what flags it.
cat > src/reports.py <<'EOF'
def overdue_invoices(invoices, as_of):
    """Invoices past their due date and still unpaid at the end of `as_of`.

    An invoice due on `as_of` is not yet overdue. An invoice paid after `as_of`
    counts as overdue on `as_of`, since it was unpaid on that day.
    """
    return [
        invoice
        for invoice in invoices
        if invoice.due_date < as_of and invoice.paid_on is None
    ]
EOF
expect 0 "function-verb: a short noun function with a long docstring is fine" --only function-verb --strict
nothas "overdue_invoices"
reset_diff

# =========================================================================
# method-names -- vague-names extended to JS/TS class methods
# =========================================================================
cat > src/methods.ts <<'EOF'
export class Orders {
  process(order: Order): void {
    save(order);
  }
  helper(): void {
    run();
  }
}
EOF
expect 1 "method-names: vague TS method names detected" --only method-names --strict
has "method named .process."
has "method named .helper."
reset_diff

cat > src/methods_ok.ts <<'EOF'
export class Orders {
  submitOrder(order: Order): void {
    save(order);
  }
}
EOF
expect 0 "method-names: intent-revealing method names are not flagged" --only method-names --strict
nothas "method named"
reset_diff

# =========================================================================
# magic-number -- unexplained literals in comparisons and timeouts
# =========================================================================
cat > src/magic.py <<'EOF'
import time


def poll(client, retries):
    if retries > 3:
        return None
    time.sleep(5)
    return client.get("/status", timeout=30)
EOF
cat > src/magic.ts <<'EOF'
export function poll(attempts: number): void {
  if (attempts >= 7) {
    return;
  }
  setTimeout(check, 2500);
  request({ timeoutMs: 30000 });
}
EOF
expect 1 "magic-number: literals in comparisons, sleep and timeouts detected (py + TS)" --only magic-number --strict
has "src/magic.py:5: magic number 3"
has "src/magic.py:7: magic number 5"
has "src/magic.py:8: magic number 30"
has "src/magic.ts:2: magic number 7"
has "src/magic.ts:5: magic number 2500"
has "src/magic.ts:6: magic number 30000"
reset_diff

cat > src/status_timeout.py <<'EOF'
def fetch_status(client):
    return client.get("/status", timeout=404)
EOF
expect 1 "magic-number: a timeout stays flagged beside a status" --only magic-number --strict
has "src/status_timeout.py:2: magic number 404"
reset_diff

mkdir -p tests
cat > src/magic_ok.py <<'EOF'
MAX_RETRIES = 5
POLL_TIMEOUT_SECONDS = 30


def poll(client, retries, rows, limit):
    if retries > MAX_RETRIES or retries == -1 or retries >= 100:
        return None
    if rows[3] > limit:
        return rows
    return client.get("/status", timeout=POLL_TIMEOUT_SECONDS)
EOF
cat > tests/test_magic_ok.py <<'EOF'
def test_total_is_forty_two():
    assert compute_total() == 42
EOF
cat > src/magic_ok.ts <<'EOF'
const MAX_ATTEMPTS = 5;
export function poll(attempts: number, items: number[], threshold: number): boolean {
  const positives = items.filter((value) => value > 0);
  return attempts === 1 || attempts > MAX_ATTEMPTS || items[4] > threshold || positives.length > 0;
}
EOF
cat > src/status_ok.py <<'EOF'
def fetch_order(resp):
    if resp.status_code == 404:
        return None
    if 500 <= resp.status <= 599 or status != 200:
        raise RuntimeError(resp.text)
    return resp.json()
EOF
cat > src/status_ok.ts <<'EOF'
export function readOrder(res: Response, statusCode: number): boolean {
  if (res.status === 404 || statusCode !== 201) {
    return false;
  }
  return 200 === res.status;
}
EOF
expect 0 "magic-number: constants, -1/0/1/100, indexes, tests, HTTP statuses not flagged" --only magic-number --strict
nothas "magic number"
reset_diff

# =========================================================================
# unsupported languages are named, not silently passed
# =========================================================================
mkdir -p app/models cmd
printf 'class User\nend\n' > app/models/user.rb
printf 'package main\n' > cmd/main.go
printf 'package main\n' > cmd/serve.go
expect 0 "unsupported: .rb/.go files are reported, exit 0" --strict
has "craft_check: 2 .go files not checked (unsupported language)"
has "craft_check: 1 .rb files not checked (unsupported language)"
reset_diff

printf 'def add(a, b):\n    return a + b\n' > src/plain.py
expect 0 "unsupported: no line when every file is a supported language" --strict
nothas "unsupported language"
reset_diff

# =========================================================================
# every check at once, --strict, on a well-written module and a React component
# =========================================================================
mkdir -p src/components
cat > src/billing.py <<'EOF'
from dataclasses import dataclass

LATE_FEE_CENTS = 500
GRACE_PERIOD_DAYS = 14


@dataclass
class Invoice:
    amount_cents: int
    days_overdue: int
    is_paid: bool = False


def calculate_late_fee(invoice):
    if invoice.is_paid or invoice.days_overdue <= GRACE_PERIOD_DAYS:
        return 0
    return LATE_FEE_CENTS


def summarize_invoices(invoices):
    total_cents = 0
    for i, invoice in enumerate(invoices):
        total_cents += invoice.amount_cents + calculate_late_fee(invoice) + i
    has_overdue = any(invoice.days_overdue > 0 for invoice in invoices)
    return total_cents, has_overdue
EOF
cat > src/components/InvoiceList.tsx <<'EOF'
const PAGE_SIZE = 25;

export function InvoiceList(props: InvoiceListProps) {
  const [isExpanded, setExpanded] = useState(props.isInitiallyExpanded);
  const visibleInvoices = isExpanded ? props.invoices : props.invoices.slice(0, PAGE_SIZE);
  const handleToggle = () => setExpanded(!isExpanded);
  return (
    <section>
      {visibleInvoices.map((invoice) => (
        <InvoiceRow key={invoice.id} invoice={invoice} />
      ))}
      <button onClick={handleToggle}>{isExpanded ? "Show fewer" : "Show all"}</button>
    </section>
  );
}

export function formatAmount(amountCents: number): string {
  return (amountCents / 100).toFixed(2);
}
EOF
expect 0 "all checks --strict: a well-named module and React component are clean" --strict
nothas "ADVISORY"
nothas "FAIL"
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
printf '\n\ndef add_unrelated(first_value, second_value):\n    return first_value + second_value\n' >> src/legacy.py
expect 0 "diff-scoping: untouched pre-existing violation is not re-flagged" --strict
nothas "legacy_vague"
git checkout -q -- src/legacy.py

echo
echo "craft_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
