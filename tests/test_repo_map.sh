#!/usr/bin/env bash
# Regression suite for scripts/repo_map.py — the fast-orientation tool.
# Asserts detection AND absence of crashes, not just happy-path output.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
RM="$ROOT/scripts/repo_map.py"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-58s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "$1"; [ -s /tmp/rm.out ] && sed 's/^/       /' /tmp/rm.out | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -q "$1" /tmp/rm.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -q "$1" /tmp/rm.out && bad "false positive: $1" || ok "no false positive: $1"; }

# ---------- runs on this repo without error ----------
python3 "$RM" "$ROOT" >/tmp/rm.out 2>&1
rc_is 0 $? "repo_map: runs clean on this repo"
no "Traceback"

# ---------- detects Python and TypeScript ----------
has "Python"
has "TypeScript"

# ---------- entry points and doc locations from this repo's own shape ----------
has "__main__ guard"
has "AGENTS.md"
has "decisions/"
has "specs/"

# ---------- --top N ----------
python3 "$RM" "$ROOT" --top 3 >/tmp/rm.out 2>&1
rc_is 0 $? "repo_map: --top 3 runs clean"
n=$(sed -n '/Most-connected files/,/^$/p' /tmp/rm.out | grep -c "importer(s)")
[ "$n" -le 3 ] && ok "repo_map: --top 3 shows at most 3 ranked files (got $n)" \
  || bad "repo_map: --top 3 showed $n ranked files"

# ---------- --symbol AuthService finds the worked example ----------
python3 "$RM" "$ROOT" --symbol AuthService >/tmp/rm.out 2>&1
rc_is 0 $? "repo_map: --symbol runs clean"
has "examples/login/src/auth.service.ts"
has "examples/login/src/auth.controller.ts"

# a symbol that does not exist must say so cleanly, not crash
python3 "$RM" "$ROOT" --symbol ThisSymbolDoesNotExistAnywhereXYZ >/tmp/rm.out 2>&1
rc_is 0 $? "repo_map: unknown symbol exits clean"
has "none found"
no "Traceback"

# ---------- ranking is deterministic across runs ----------
python3 "$RM" "$ROOT" --top 20 >/tmp/rm1.out 2>&1
python3 "$RM" "$ROOT" --top 20 >/tmp/rm2.out 2>&1
if diff -q /tmp/rm1.out /tmp/rm2.out >/dev/null; then
  ok "repo_map: identical output across two runs"
else
  FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "repo_map: output differs across runs"
  diff /tmp/rm1.out /tmp/rm2.out | head -10 | sed 's/^/       /'
fi

# ---------- a small, controlled fixture: known import edges ----------
FX="$TMP/fixture"
mkdir -p "$FX/src"
cat > "$FX/src/util.py" <<'PY'
def helper():
    return 1
PY
cat > "$FX/src/a.py" <<'PY'
from src.util import helper
def a():
    return helper()
PY
cat > "$FX/src/b.py" <<'PY'
from src.util import helper
def b():
    return helper()
PY
cat > "$FX/src/service.ts" <<'TS'
export class WidgetService {
  make() { return 1; }
}
TS
cat > "$FX/src/controller.ts" <<'TS'
import { WidgetService } from './service';
export class WidgetController {
  constructor(private svc: WidgetService) {}
}
TS
python3 "$RM" "$FX" --json >/tmp/rm.out 2>&1
rc_is 0 $? "repo_map: --json runs clean on fixture"
python3 -c "import json; json.load(open('/tmp/rm.out'))" >/tmp/rm.parse 2>&1
rc_is 0 $? "repo_map: --json emits valid JSON"

python3 - "$FX" "$RM" <<'PYEOF' >/tmp/rm.out 2>&1
import json, subprocess, sys
root, rm = sys.argv[1], sys.argv[2]
out = subprocess.run(["python3", rm, root, "--json"], capture_output=True, text=True).stdout
d = json.loads(out)
ranked = {r["file"]: r["in_degree"] for r in d["ranking"]}
assert ranked.get("src/util.py") == 2, ranked
assert ranked.get("src/service.ts") == 1, ranked
print("util.py in-degree 2, service.ts in-degree 1 -- as expected")
PYEOF
rc_is 0 $? "repo_map: import graph resolves known Python and TS edges"
has "as expected"

# ---------- empty dir gives a clean message, not a traceback ----------
mkdir -p "$TMP/empty"
python3 "$RM" "$TMP/empty" >/tmp/rm.out 2>&1
rc_is 0 $? "repo_map: empty dir exits clean"
has "no recognized source files"
no "Traceback"

# ---------- nonexistent path is reported, not a traceback ----------
python3 "$RM" "$TMP/does-not-exist" >/tmp/rm.out 2>&1
rc_is 1 $? "repo_map: nonexistent path exits 1"
has "no such path"
no "Traceback"

echo
echo "repo_map: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
