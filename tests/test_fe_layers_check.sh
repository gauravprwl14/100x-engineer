#!/usr/bin/env bash
# Regression suite for fe_layers_check.py. For every check: a planted violation
# AND a clean file that must NOT be flagged. The clean-file assertions are the
# important half -- a layering checker with false positives gets disabled.
# Run: bash tests/test_fe_layers_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FC="$ROOT/scripts/fe_layers_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src
printf 'export const noop = () => {}\n' > src/keep.ts
git add -A; git commit -qm init >/dev/null

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [--only X ...]
  local exp="$1" label="$2"; shift 2
  python3 "$FC" "$@" >/tmp/fc.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-56s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-56s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' /tmp/fc.out; fi
}
has() { grep -q -- "$1" /tmp/fc.out && { PASS=$((PASS+1)); printf '  ok   %-56s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "NOT reported: $1"; }; }
nothas() { grep -q -- "$1" /tmp/fc.out && { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "false positive: $1"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-56s\n' "no false positive: $1"; }; }
reset_diff() { git checkout -q -- . ; git clean -qfd . ; }

# =========================================================================
# presentation-io -- fetch/axios/.then/*Api./*Client./raw URL in a .tsx
# =========================================================================
cat > src/OrderList.tsx <<'EOF'
export function OrderList() {
  const [orders, setOrders] = useState([]);
  useEffect(() => {
    fetch('/api/orders').then((r) => r.json()).then(setOrders);
  }, []);
  return <ul>{orders.map((o) => <li key={o.id}>{o.name}</li>)}</ul>;
}
EOF
expect 1 "presentation-io: fetch()+.then() in component detected" --only presentation-io --strict
has "presentation layer performing I/O"
reset_diff

cat > src/UserBadge.tsx <<'EOF'
export function UserBadge({ userApi }: { userApi: UserApi }) {
  const handleClick = () => userApi.refresh();
  return <button onClick={handleClick}>Refresh</button>;
}
EOF
expect 1 "presentation-io: component calling an *Api. client method directly detected" --only presentation-io --strict
has "presentation layer performing I/O"
reset_diff

cat > src/Analytics.tsx <<'EOF'
export function Analytics({ onTrack }: { onTrack: () => void }) {
  const handleClick = () => onTrack();
  return <button onClick={handleClick}>Go</button>;
}
EOF
expect 0 "presentation-io: a plain callback prop call is not flagged" --only presentation-io --strict
nothas "Analytics.tsx"
reset_diff

cat > src/ProfileCard.tsx <<'EOF'
import { useProfile } from './useProfile';

export function ProfileCard({ name, avatarUrl }: { name: string; avatarUrl: string }) {
  return (
    <div>
      <img src="https://cdn.example.com/avatar.png" alt={name} />
      <a href="https://example.com/help">Help</a>
      <span>{name}</span>
    </div>
  );
}
EOF
expect 0 "presentation-io: href/src URL attributes are not flagged" --only presentation-io --strict
nothas "ProfileCard.tsx"
reset_diff

cat > src/PriceTag.ts <<'EOF'
import Foo from './api/total/price';
export const x = Foo;
EOF
mkdir -p src/domain
cat > src/domain/pricing.ts <<'EOF'
export function addTax(total: number, tax: number): number {
  return total + tax;
}
EOF
expect 0 "presentation-io: only scans .tsx, plain .ts import paths never checked" --only presentation-io --strict
reset_diff
rm -rf src/domain

# =========================================================================
# presentation-money-math -- arithmetic on price/amount/total/tax/discount/fee
# =========================================================================
cat > src/Cart.tsx <<'EOF'
export function Cart({ items }: { items: Item[] }) {
  const total = items.reduce((acc, i) => acc + i.price, 0);
  const grandTotal = total + tax;
  return <div>{grandTotal}</div>;
}
EOF
expect 1 "presentation-money-math: total + tax in component detected" --only presentation-money-math --strict
has "business rule in the presentation layer"
reset_diff

cat > src/ReceiptLine.tsx <<'EOF'
export function ReceiptLine({ total }: { total: number }) {
  return <div>{`Total: ${total}`}</div>;
}
EOF
expect 0 "presentation-money-math: template-literal display of total is not flagged" --only presentation-money-math --strict
nothas "ReceiptLine.tsx"
reset_diff

cat > src/Banner.tsx <<'EOF'
export function Banner({ total }: { total: number }) {
  return <div>{"Total: " + total}</div>;
}
EOF
expect 0 "presentation-money-math: string concatenation with total is not flagged" --only presentation-money-math --strict
nothas "Banner.tsx"
reset_diff

cat > src/Grid.tsx <<'EOF'
export function Grid({ columns, rows }: { columns: number; rows: number }) {
  const cellCount = columns * rows;
  return <div data-count={cellCount} />;
}
EOF
expect 0 "presentation-money-math: non-money arithmetic (columns*rows) is not flagged" --only presentation-money-math --strict
nothas "Grid.tsx"
reset_diff

# =========================================================================
# large-use-effect -- useEffect body over the line threshold
# =========================================================================
python3 - <<'PYEOF'
lines = ["export function Big() {", "  useEffect(() => {"]
lines += [f"    doThing({i});" for i in range(20)]
lines += ["  }, []);", "  return <div />;", "}"]
open("src/Big.tsx", "w").write("\n".join(lines) + "\n")
PYEOF
expect 1 "large-use-effect: 20-line effect body detected" --only large-use-effect --strict
has "logic belongs in a hook"
reset_diff

cat > src/Small.tsx <<'EOF'
export function Small() {
  useEffect(() => {
    document.title = 'Small';
  }, []);
  return <div />;
}
EOF
expect 0 "large-use-effect: 1-line effect body is not flagged" --only large-use-effect --strict
nothas "Small.tsx"
reset_diff

# =========================================================================
# business-imports-react -- a domain/lib/core/business .ts importing react/next/DOM
# =========================================================================
mkdir -p src/domain
cat > src/domain/pricing.ts <<'EOF'
import { useState } from 'react';
export function computeTotal(items: Item[]): number {
  return items.reduce((acc, i) => acc + i.price, 0);
}
EOF
expect 1 "business-imports-react: domain/ .ts importing react detected" --only business-imports-react --strict
has "dependency direction reversed"
reset_diff
rm -rf src/domain

mkdir -p src/domain
cat > src/domain/eligibility.ts <<'EOF'
export function isEligible(balance: number): boolean {
  return balance > 0;
}
EOF
expect 0 "business-imports-react: pure domain module is not flagged" --only business-imports-react --strict
nothas "eligibility.ts"
reset_diff
rm -rf src/domain

mkdir -p src/components
cat > src/components/Widget.ts <<'EOF'
import { useState } from 'react';
export function useWidgetHelper() {
  return useState(0);
}
EOF
expect 0 "business-imports-react: react import outside domain/lib/core/business is not flagged" --only business-imports-react --strict
nothas "Widget.ts"
reset_diff
rm -rf src/components

mkdir -p src/lib
cat > src/lib/format.ts <<'EOF'
export function formatCurrency(cents: number): string {
  return (cents / 100).toFixed(2);
}
EOF
cat > src/lib/format.tsx <<'EOF'
export function FormatPreview() { return null; }
EOF
expect 0 "business-imports-react: .ts with a same-stem .tsx sibling is exempted" --only business-imports-react --strict
nothas "lib/format.ts"
reset_diff
rm -rf src/lib

# =========================================================================
# container-presenter-fused -- big file, JSX, many use* calls
# =========================================================================
python3 - <<'PYEOF'
lines = ["export function Dashboard() {"]
lines += ["  const [a, setA] = useState(0);", "  const [b, setB] = useState(0);",
          "  const c = useMemo(() => a + b, [a, b]);", "  useEffect(() => { setA(1); }, []);"]
lines += [f"  const v{i} = {i};" for i in range(210)]
lines += ["  return <div>{a}{b}{c}</div>;", "}"]
open("src/Dashboard.tsx", "w").write("\n".join(lines) + "\n")
PYEOF
expect 1 "container-presenter-fused: 200+ line file with 4 use* calls and JSX detected" --only container-presenter-fused --strict
has "container and presenter fused"
reset_diff

python3 - <<'PYEOF'
lines = ["export function PlainList({ items }) {"]
lines += [f"  // filler line {i}" for i in range(210)]
lines += ["  return <ul>{items.map((x) => <li key={x.id}>{x.name}</li>)}</ul>;", "}"]
open("src/PlainList.tsx", "w").write("\n".join(lines) + "\n")
PYEOF
expect 0 "container-presenter-fused: 200+ line file with 0 use* calls is not flagged" --only container-presenter-fused --strict
nothas "PlainList.tsx"
reset_diff

# =========================================================================
# presentation-storage-access -- localStorage/sessionStorage/document.cookie in a .tsx
# =========================================================================
cat > src/Theme.tsx <<'EOF'
export function Theme() {
  const saved = localStorage.getItem('theme');
  return <div>{saved}</div>;
}
EOF
expect 1 "presentation-storage-access: localStorage.getItem in component detected" --only presentation-storage-access --strict
has "storage access belongs behind the logic layer"
reset_diff

cat > src/ThemeClean.tsx <<'EOF'
export function ThemeClean({ theme }: { theme: string }) {
  return <div className={theme}>hi</div>;
}
EOF
expect 0 "presentation-storage-access: no storage access is not flagged" --only presentation-storage-access --strict
nothas "ThemeClean.tsx"
reset_diff

# =========================================================================
# presentation-inline-validation -- .tsx importing zod/yup/joi and calling .parse/.validate
# =========================================================================
cat > src/SignupForm.tsx <<'EOF'
import { z } from 'zod';
const schema = z.object({ email: z.string() });
export function SignupForm({ raw }: { raw: unknown }) {
  const parsed = schema.parse(raw);
  return <div>{parsed.email}</div>;
}
EOF
expect 1 "presentation-inline-validation: schema.parse() called in component detected" --only presentation-inline-validation --strict
has "validation belongs in the business layer"
reset_diff

cat > src/SignupFormClean.tsx <<'EOF'
export function SignupFormClean({ email, error }: { email: string; error?: string }) {
  return <div>{error ?? email}</div>;
}
EOF
expect 0 "presentation-inline-validation: no validation import is not flagged" --only presentation-inline-validation --strict
nothas "SignupFormClean.tsx"
reset_diff

# =========================================================================
# hook-renders-jsx -- a use*.ts hook file containing JSX
# =========================================================================
cat > src/useBadHook.ts <<'EOF'
export function useBadHook() {
  return <div>not allowed here</div>;
}
EOF
expect 1 "hook-renders-jsx: JSX in a use*.ts hook file detected" --only hook-renders-jsx --strict
has "logic layer rendering"
reset_diff

cat > src/useGoodHook.ts <<'EOF'
export function useGoodHook() {
  const [value, setValue] = useState(0);
  return { value, setValue };
}
EOF
expect 0 "hook-renders-jsx: hook returning data only is not flagged" --only hook-renders-jsx --strict
nothas "useGoodHook.ts"
reset_diff

# =========================================================================
# --list, --only unknown, no changes
# =========================================================================
expect 0 "--list exits 0" --list >/dev/null
python3 "$FC" --list | grep -q "presentation-io (blocking)" \
  && { PASS=$((PASS+1)); printf '  ok   %-56s\n' "--list marks presentation-io blocking"; } \
  || { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "--list did not mark presentation-io blocking"; }

python3 "$FC" --only bogus-check >/tmp/fc.out 2>&1
[ $? -eq 2 ] && { PASS=$((PASS+1)); printf '  ok   %-56s\n' "unknown --only check exits 2"; } \
             || { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "unknown --only check did not exit 2"; }

reset_diff
python3 "$FC" >/tmp/fc.out 2>&1
grep -q "no changes to inspect" /tmp/fc.out \
  && { PASS=$((PASS+1)); printf '  ok   %-56s\n' "no diff reports no changes"; } \
  || { FAIL=$((FAIL+1)); printf '  FAIL %-56s\n' "no diff did not report no changes"; }

echo
echo "fe_layers_check tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
