#!/usr/bin/env bash
# Regression suite for perf_check.py. Asserts detection AND absence of false
# positives -- the clean-file half is the important one, per the script's own
# docstring: a tool that cries wolf on ordinary code gets deleted.
# Run: bash tests/test_perf_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PC="$ROOT/scripts/perf_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src
printf 'def noop():\n    return 1\n' > src/base.py
git add -A; git commit -qm init

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [--only X]
  local exp="$1" label="$2"; shift 2
  python3 "$PC" "$@" >/tmp/pc.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-55s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-55s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' /tmp/pc.out; fi
}
has() { grep -q "$1" /tmp/pc.out && { PASS=$((PASS+1)); printf '  ok   %-55s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "NOT reported: $1"; }; }
nothas() { grep -q "$1" /tmp/pc.out && { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "false positive: $1"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-55s\n' "no false positive: $1"; }; }
reset_diff() { git add -A >/dev/null 2>&1; git commit -qm wip >/dev/null 2>&1; }

# ============================================================ n-plus-one ====
printf 'async def load(ids):\n    out = []\n    for i in ids:\n        row = await db.fetch(i)\n        out.append(row)\n    return out\n' > src/np_await.py
expect 1 "n-plus-one: await in for-loop (py)" --only n-plus-one
has "await inside a loop"
reset_diff

printf 'def load(ids):\n    out = []\n    for i in ids:\n        obj = Model.objects.get(id=i)\n        out.append(obj)\n    return out\n' > src/np_sync.py
expect 1 "n-plus-one: sync ORM call in loop (py)" --only n-plus-one
has "objects.get"
reset_diff

cat > src/np_js.js << 'EOF'
async function loadAll(ids) {
  const out = [];
  for (const id of ids) {
    const row = await fetch(`/api/items/${id}`);
    out.push(row);
  }
  return out;
}
EOF
expect 1 "n-plus-one: await in for-of (js)" --only n-plus-one
has "np_js.js"
reset_diff

cat > src/np_map.js << 'EOF'
function loadAll(ids) {
  return ids.map(async (id) => {
    const row = await fetch(`/api/items/${id}`);
    return row;
  });
}
EOF
expect 1 "n-plus-one: await in .map callback (js)" --only n-plus-one
has "np_map.js"
reset_diff

# clean: pure compute loop, no I/O
printf 'def total(items):\n    out = 0\n    for x in items:\n        out += x\n    return out\n' > src/clean_loop.py
expect 0 "n-plus-one: pure compute loop is clean (py)" --only n-plus-one
reset_diff

printf 'function doubled(items) {\n  return items.map((x) => x * 2);\n}\n' > src/clean_map.js
expect 0 "n-plus-one: plain .map with no I/O is clean (js)" --only n-plus-one
reset_diff

cat > src/clean_promise_all.js << 'EOF'
async function loadAll(ids) {
  return Promise.all(ids.map(async (id) => {
    const row = await fetch(`/api/items/${id}`);
    return row;
  }));
}
EOF
expect 0 "n-plus-one: Promise.all(x.map(async..)) is the fix, not the bug (js)" --only n-plus-one
reset_diff

# ======================================================= unbounded-query ====
printf 'def list_users():\n    return User.objects.all()\n' > src/uq_bad.py
expect 0 "unbounded-query: no limit is advisory, exits 0" --only unbounded-query
has "no limit"
reset_diff

printf 'def list_users():\n    return User.objects.all()[:100]\n' > src/uq_ok.py
expect 0 "unbounded-query: sliced query is clean" --only unbounded-query
reset_diff

cat > src/uq_arr.js << 'EOF'
function getUsers() {
  return Model.find({ active: true });
}
function pickOne(items, id) {
  return items.find(x => x.id === id);
}
EOF
expect 0 "unbounded-query: Model.find({}) flagged, Array.find() is not"
has "Model.find"
nothas "pickOne"
reset_diff

# ========================================================= hot-path-sort ====
printf 'def get_sorted():\n    users = User.objects.all()\n    return sorted(users, key=lambda u: u.name)\n' > src/hp_bad.py
expect 0 "hot-path-sort: sort over unbounded fetch is advisory" --only hot-path-sort
has "just-fetched unbounded"
reset_diff

printf 'def get_sorted():\n    users = User.objects.all()[:50]\n    return sorted(users, key=lambda u: u.name)\n' > src/hp_ok.py
expect 0 "hot-path-sort: sort over a limited fetch is clean" --only hot-path-sort
reset_diff

# =========================================================== select-star ====
printf 'cursor.execute("SELECT * FROM users WHERE id = %%s", (uid,))\n' > src/ss_bad.py
expect 0 "select-star: advisory" --only select-star
has "SELECT \*"
reset_diff

printf 'cursor.execute("SELECT id, name FROM users WHERE id = %%s", (uid,))\n' > src/ss_ok.py
expect 0 "select-star: explicit columns is clean" --only select-star
reset_diff

# ============================================================= no-timeout ===
printf 'def fetch_user(uid):\n    return requests.get(f"https://api.example.com/users/{uid}")\n' > src/nt_bad.py
expect 1 "no-timeout: requests.get with no timeout (py)" --only no-timeout
has "no timeout"
reset_diff

printf 'def fetch_user(uid):\n    return requests.get(f"https://api.example.com/users/{uid}", timeout=5)\n' > src/nt_ok.py
expect 0 "no-timeout: requests.get with timeout is clean" --only no-timeout
reset_diff

cat > src/nt_bad.js << 'EOF'
async function fetchUser(id) {
  return fetch(`https://api.example.com/users/${id}`);
}
EOF
expect 1 "no-timeout: bare fetch (js)" --only no-timeout
has "nt_bad.js"
reset_diff

cat > src/nt_ok.js << 'EOF'
async function fetchUser(id) {
  const controller = new AbortController();
  return fetch(`https://api.example.com/users/${id}`, { signal: controller.signal });
}
EOF
expect 0 "no-timeout: fetch with AbortController signal is clean" --only no-timeout
reset_diff

# ================================================ unbounded-accumulation ====
printf 'def collect():\n    results = []\n    for row in cursor.fetchall():\n        results.append(row)\n    return results\n' > src/ua_bad.py
expect 0 "unbounded-accumulation: advisory" --only unbounded-accumulation
has "unbounded accumulation"
reset_diff

printf 'def collect():\n    results = []\n    for row in cursor.fetchall():\n        if len(results) >= 100:\n            break\n        results.append(row)\n    return results\n' > src/ua_cap.py
expect 0 "unbounded-accumulation: capped with break is clean" --only unbounded-accumulation
reset_diff

printf 'def collect(items):\n    results = []\n    for x in items:\n        results.append(x * 2)\n    return results\n' > src/ua_notquery.py
expect 0 "unbounded-accumulation: loop not over a query result is clean" --only unbounded-accumulation
reset_diff

cat > src/ua_bad.js << 'EOF'
async function collect() {
  const results = [];
  for (const row of db.users.find({})) {
    results.push(row);
  }
  return results;
}
EOF
expect 0 "unbounded-accumulation: push in query-result for-of (js)" --only unbounded-accumulation
has "ua_bad.js"
reset_diff

# ================================================ unbounded-concurrency =====
cat > src/uc_bad.js << 'EOF'
async function loadAll(ids) {
  return Promise.all(ids.map((id) => fetch(`/api/items/${id}`)));
}
EOF
expect 0 "unbounded-concurrency: Promise.all(x.map()) is advisory" --only unbounded-concurrency
has "Promise.all"
reset_diff

cat > src/uc_ok.js << 'EOF'
async function loadAll(ids) {
  return Promise.all(chunk(ids, 10).map((id) => fetch(`/api/items/${id}`)));
}
EOF
expect 0 "unbounded-concurrency: chunked collection is clean" --only unbounded-concurrency
reset_diff

printf 'async def load_all(ids):\n    return await asyncio.gather(*[fetch(i) for i in ids])\n' > src/uc_bad.py
expect 0 "unbounded-concurrency: gather over comprehension is advisory (py)" --only unbounded-concurrency
has "asyncio.gather"
reset_diff

printf 'async def load_pair():\n    return await asyncio.gather(fetch_a(), fetch_b())\n' > src/uc_ok.py
expect 0 "unbounded-concurrency: gather over fixed args is clean (py)" --only unbounded-concurrency
reset_diff

# =================================================== heavy-dependency =======
cat > package.json << 'EOF'
{
  "name": "x",
  "dependencies": {
    "moment": "^2.29.4",
    "dayjs": "^1.11.0"
  }
}
EOF
expect 0 "heavy-dependency: moment flagged, dayjs is not" --only heavy-dependency
has "moment"
nothas "\`dayjs\`"
reset_diff

cat > requirements.txt << 'EOF'
torch==2.1.0
requests==2.31.0
EOF
expect 0 "heavy-dependency: torch flagged, requests is not (py)" --only heavy-dependency
has "torch"
nothas "\`requests\`"
reset_diff

cat > package.json << 'EOF'
{
  "name": "x",
  "dependencies": {
    "lodash-es": "^4.17.21"
  }
}
EOF
expect 0 "heavy-dependency: lodash-es (tree-shakeable) is not lodash" --only heavy-dependency
reset_diff

# ============================================================ full clean ====
printf 'def add(a, b):\n    return a + b\n' > src/final_clean.py
printf 'export function add(a, b) {\n  return a + b;\n}\n' > src/final_clean.js
expect 0 "full run: entirely clean diff produces no findings"

echo
echo "perf_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
