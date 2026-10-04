#!/usr/bin/env bash
# Every diff checker must see the same diff whether it is run from the repo root
# or from a monorepo subfolder, and must refuse (exit 2) rather than pass when
# there is no git repository or the --base ref does not resolve.
#
# The defects are introduced by MODIFYING committed files: `git diff` reports
# those root-relative, which is the path a subfolder run used to fail to read.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; NOREPO="$(mktemp -d)"
trap 'rm -rf "$TMP" "$OUT" "$NOREPO"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-64s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "$1"; sed 's/^/       /' "$OUT/r.out" | head -8; }
# run <exp-exit> <label> <dir> <tool> [args...]
run() {
  local exp="$1" label="$2" dir="$3" tool="$4"; shift 4
  ( cd "$dir" && python3 "$ROOT/scripts/$tool.py" "$@" ) >"$OUT/r.out" 2>&1; local got=$?
  [ "$got" -eq "$exp" ] && ok "$label" || bad "$label (exit exp=$exp got=$got)"
}
has() { grep -q -- "$1" "$OUT/r.out" && ok "  reports $1" || bad "  NOT reported: $1"; }

cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
W=apps/web
mkdir -p "$W/src/components" "$W/tests" "$W/tools"
echo 'export const Card = ({ f }) => <button onClick={f}>x</button>;' > "$W/src/Card.tsx"
printf "it('adds', () => {\n  expect(add(1, 2)).toBe(3);\n});\n" > "$W/src/add.test.ts"
printf 'def run():\n    try:\n        go()\n    except ValueError:\n        raise\n' > "$W/tools/job.py"
printf "'use client';\nexport function List({ items }) {\n  return <ul>{items}</ul>;\n}\n" > "$W/src/components/List.tsx"
printf 'async def load(ids):\n    return await db.fetch_many(ids)\n' > "$W/tools/load.py"
printf 'def test_ready():\n    assert ready()\n' > "$W/tests/test_ready.py"
printf 'export function total(xs: number[]) {\n  return xs.length;\n}\n' > "$W/src/orders.ts"
git add -A; git commit -qm init

# --- clean tree: quiet from the subfolder, no false positive ---
for tool in a11y_check bloat_check craft_check fe_layers_check perf_check test_design_check review_scope; do
  run 0 "$tool: clean tree from subfolder exits 0" "$TMP/$W" "$tool"
done

# --- introduce one defect per checker, all by modifying tracked files ---
echo 'export const Card = ({ f }) => <div onClick={f}>x</div>;' > "$W/src/Card.tsx"
printf "it('adds', () => {\n  add(1, 2);\n});\n" > "$W/src/add.test.ts"
printf 'def run():\n    try:\n        go()\n    except:\n        pass\n' > "$W/tools/job.py"
cat > "$W/src/components/List.tsx" <<'EOF'
'use client';
export function List() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    fetch('/api/items').then((r) => r.json()).then(setItems);
  }, []);
  return <ul>{items}</ul>;
}
EOF
printf 'async def load(ids):\n    out = []\n    for i in ids:\n        out.append(await db.fetch(i))\n    return out\n' > "$W/tools/load.py"
printf 'import time\ndef test_ready():\n    time.sleep(2)\n    assert ready()\n' > "$W/tests/test_ready.py"
cat > "$W/src/orders.ts" <<'EOF'
export async function getInvoice(id: string) {
  return db.invoices.findOne(id);
}
EOF

check() { # check <tool> <finding> [args...]
  local tool="$1" finding="$2"; shift 2
  run 1 "$tool: defect detected from repo root" "$TMP" "$tool" "$@"; has "$finding"
  run 1 "$tool: same defect detected from $W" "$TMP/$W" "$tool" "$@"; has "$finding"
}
check a11y_check       "$W/src/Card.tsx"
check bloat_check      "$W/src/add.test.ts"   --only assertionless
check craft_check      "$W/tools/job.py"
check fe_layers_check  "$W/src/components/List.tsx" --only presentation-io
check perf_check       "$W/tools/load.py"     --only n-plus-one
check test_design_check "$W/tests/test_ready.py" --only sleep

# review_scope always exits 0; detection is naming the file under a question.
run 0 "review_scope: runs from repo root" "$TMP" review_scope; has "$W/src/orders.ts"
run 0 "review_scope: runs from $W" "$TMP/$W" review_scope; has "$W/src/orders.ts"

# --- no repository, or a --base that does not resolve: refuse, never pass ---
for tool in a11y_check bloat_check craft_check fe_layers_check perf_check test_design_check review_scope; do
  run 2 "$tool: outside a git repo exits 2" "$NOREPO" "$tool"; has "not inside a git repository"
  run 2 "$tool: unresolvable --base exits 2" "$TMP/$W" "$tool" --base no-such-ref; has "does not resolve"
done

echo
echo "git_root tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
