#!/usr/bin/env bash
# Every diff checker must see the same diff whether it is run from the repo root
# or from a monorepo subfolder, and must refuse (exit 2) rather than pass when
# there is no git repository or the --base ref does not resolve.
#
# The defects are introduced by MODIFYING committed files: `git diff` reports
# those root-relative, which is the path a subfolder run used to fail to read.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; NOREPO="$(mktemp -d)"; T2="$(mktemp -d)"; UNBORN="$(mktemp -d)"
trap 'chmod -R u+rw "$UNBORN" 2>/dev/null; rm -rf "$TMP" "$OUT" "$NOREPO" "$T2" "$UNBORN"' EXIT
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
for tool in a11y_check bloat_check craft_check fe_layers_check perf_check test_design_check review_scope schema_check appsec_check ui_baseline_check; do
  run 2 "$tool: outside a git repo exits 2" "$NOREPO" "$tool"; has "not inside a git repository"
  run 2 "$tool: unresolvable --base exits 2" "$TMP/$W" "$tool" --base no-such-ref; has "does not resolve"
done

# --- schema_check: the same diff from the root and from a subfolder ---
mkdir -p "$TMP/apps/api/migrations"
printf -- '-- users migrations\n' > "$TMP/apps/api/migrations/000.sql"
( cd "$TMP" && git add -A && git commit -qm schema )
cat > "$TMP/apps/api/migrations/000.sql" <<'EOF'
-- users migrations
ALTER TABLE users DROP COLUMN legacy;
ALTER TABLE users ADD COLUMN plan TEXT NOT NULL;
EOF
for d in "$TMP" "$TMP/apps/api"; do
  run 1 "schema_check: DROP + NOT NULL detected from ${d#$TMP}/" "$d" schema_check
  has "not-null-no-default"; has "expand-contract"
done

# --- renamed+modified and non-ASCII paths are scanned (git diff -z -M) ---
INJ='export async function f(db, id) {\n  await db.query(`SELECT * FROM t WHERE id = ${id}`);\n}\n'
cd "$T2"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src
{ printf 'export async function find(db, id) {\n'
  for i in 1 2 3 4 5 6 7 8 9 10; do printf "  await db.query('SELECT %s FROM t WHERE id = \$1', [id]);\n" "$i"; done
  printf '}\n'; } > src/old_db.ts
printf "$INJ" > src/legacy.ts
printf 'export const ok = 1;\n' > src/café.ts
git add -A; git commit -qm init
git mv src/old_db.ts src/new_db.ts
printf "$INJ" >> src/new_db.ts
run 1 "appsec_check: SQL injection in a renamed+modified file" "$T2" appsec_check --only sql-concat
has "src/new_db.ts:14"
git add -A; git commit -qm rename
printf "$INJ" > src/café.ts
run 1 "appsec_check: SQL injection in a modified non-ASCII path" "$T2" appsec_check --only sql-concat
has "src/café.ts:2"
git checkout -q -- src/café.ts
printf "$INJ" > src/naïve.ts
run 1 "appsec_check: SQL injection in an untracked non-ASCII path" "$T2" appsec_check --only sql-concat
has "src/naïve.ts:2"
git clean -qf src
git mv src/legacy.ts src/legacy_renamed.ts
run 0 "appsec_check: pure rename of pre-existing code is not re-flagged" "$T2" appsec_check --only sql-concat --strict

# --- unborn HEAD: staged files in a repo with no commit are diffed vs the empty tree ---
cd "$UNBORN"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src migrations
printf "$INJ" > src/db.ts
printf 'def run():\n    try:\n        go()\n    except:\n        pass\n' > src/job.py
git add -A
run 1 "appsec_check: unborn HEAD, staged SQL injection detected" "$UNBORN" appsec_check --only sql-concat
has "src/db.ts:2"
run 1 "craft_check: unborn HEAD, staged bare except detected" "$UNBORN" craft_check
has "src/job.py"
printf 'ALTER TABLE users ADD COLUMN plan TEXT NOT NULL;\n' > migrations/001.sql
git add migrations
run 1 "schema_check: unborn HEAD, staged migration detected" "$UNBORN" schema_check
has "not-null-no-default"

# --- a changed file that cannot be read is an error, never a skip ---
if [ "$(id -u)" -ne 0 ]; then
  printf 'ALTER TABLE users ADD COLUMN nick TEXT;\n' > "$UNBORN/migrations/002.sql"
  chmod a-r "$UNBORN/migrations/002.sql"
  for tool in schema_check appsec_check bloat_check; do
    run 2 "$tool: unreadable changed file exits 2" "$UNBORN" "$tool"; has "cannot read"
  done
  chmod u+r "$UNBORN/migrations/002.sql"
fi

echo
echo "git_root tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
