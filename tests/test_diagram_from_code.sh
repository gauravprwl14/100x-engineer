#!/usr/bin/env bash
# Regression suite for diagram_from_code.py: code -> mermaid, at selectable detail.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
D="$ROOT/scripts/diagram_from_code.py"
DD="$ROOT/scripts/design_drift.py"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-58s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "$1"; [ -s /tmp/dfc.out ] && sed 's/^/       /' /tmp/dfc.out | head -10; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -q "$1" /tmp/dfc.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -q "$1" /tmp/dfc.out && bad "false positive: $1" || ok "no false positive: $1"; }

# ---------- level 1 < level 2 < level 3 (same input, node_count from --json) ----------
python3 "$D" "$ROOT/examples/login/src" --kind sequence --level 1 --no-mmdc --json >/tmp/dfc.out 2>&1
n1=$(python3 -c "import json;print(json.load(open('/tmp/dfc.out'))['node_count'])" 2>/dev/null)
python3 "$D" "$ROOT/examples/login/src" --kind sequence --level 2 --no-mmdc --json >/tmp/dfc.out 2>&1
n2=$(python3 -c "import json;print(json.load(open('/tmp/dfc.out'))['node_count'])" 2>/dev/null)
python3 "$D" "$ROOT/examples/login/src" --kind sequence --level 3 --no-mmdc --json >/tmp/dfc.out 2>&1
n3=$(python3 -c "import json;print(json.load(open('/tmp/dfc.out'))['node_count'])" 2>/dev/null)
if [ -n "$n1" ] && [ -n "$n2" ] && [ -n "$n3" ] && [ "$n1" -lt "$n2" ] && [ "$n2" -lt "$n3" ]; then
  ok "level 1 ($n1) < level 2 ($n2) < level 3 ($n3) node counts"
else
  bad "level node counts not strictly increasing (l1=$n1 l2=$n2 l3=$n3)"
fi

# ---------- Python: 3-class call chain ----------
mkdir -p "$TMP/py"
cat > "$TMP/py/service.py" <<'PY'
class UserRepository:
    def find_by_email(self, email):
        return {"id": "u1", "email": email}


class PasswordHasher:
    def verify(self, hashed, plain):
        return True


class AuthService:
    def __init__(self, users: UserRepository, hasher: PasswordHasher):
        self.users = users
        self.hasher = hasher

    def login(self, email, password):
        user = self.users.find_by_email(email)
        ok = self.hasher.verify(user["id"], password)
        if not ok:
            raise ValueError("bad credentials")
        return user
PY
python3 "$D" "$TMP/py" --kind sequence --level 2 --entry "AuthService.login" --no-mmdc >/tmp/dfc.out 2>&1
rc_is 0 $? "python: 3-class chain diagrams cleanly"
has "AuthService"
has "UserRepository"
has "PasswordHasher"
has "find_by_email"
has "verify"
grep -q "AuthService->>UserRepository" /tmp/dfc.out && ok "python: edge AuthService->UserRepository" \
  || bad "python: missing edge AuthService->UserRepository"
grep -q "AuthService->>PasswordHasher" /tmp/dfc.out && ok "python: edge AuthService->PasswordHasher" \
  || bad "python: missing edge AuthService->PasswordHasher"
grep -q "language: python -- properly supported" /tmp/dfc.out && ok "python: labelled properly-supported" \
  || bad "python: not labelled properly-supported"

# ---------- TS: NestJS fixture ----------
python3 "$D" "$ROOT/examples/login/src" --kind sequence --level 2 --no-mmdc >/tmp/dfc.out 2>&1
rc_is 0 $? "ts: NestJS login fixture diagrams cleanly"
has "AuthController"
has "AuthService"
has "PasswordHasher"
has "SessionStore"
has "UserRepository"
grep -q "AuthController->>AuthService" /tmp/dfc.out && ok "ts: edge AuthController->AuthService" \
  || bad "ts: missing edge AuthController->AuthService"
grep -q "AuthService->>PasswordHasher" /tmp/dfc.out && ok "ts: edge AuthService->PasswordHasher" \
  || bad "ts: missing edge AuthService->PasswordHasher"
grep -q "AuthService->>SessionStore" /tmp/dfc.out && ok "ts: edge AuthService->SessionStore" \
  || bad "ts: missing edge AuthService->SessionStore"
grep -q "AuthService->>UserRepository" /tmp/dfc.out && ok "ts: edge AuthService->UserRepository" \
  || bad "ts: missing edge AuthService->UserRepository"
grep -q "language: ts -- heuristic" /tmp/dfc.out && ok "ts: labelled heuristic" \
  || bad "ts: not labelled heuristic"

# ---------- round-trip with design_drift.py ----------
python3 "$D" "$ROOT/examples/login/src" --kind sequence --level 2 --no-mmdc --json >/tmp/dfc.json 2>&1
python3 - "$TMP/rt_spec.md" <<'PYEOF'
import json, sys
d = json.load(open("/tmp/dfc.json"))
out = sys.argv[1]
with open(out, "w") as f:
    f.write("# Login (generated)\n\n```mermaid\n")
    f.write(d["mermaid"])
    f.write("\n```\n")
PYEOF
python3 "$DD" "$TMP/rt_spec.md" "$ROOT/examples/login/src" >/tmp/dfc.out 2>&1
rc_is 0 $? "round-trip: generated level-2 diagram vs its own code -> no drift"
has "no drift"
no "\[DRIFT\]"

# ---------- unresolved calls marked, not dropped ----------
mkdir -p "$TMP/unresolved"
cat > "$TMP/unresolved/plugin.py" <<'PY'
class Worker:
    def __init__(self, registry):
        self.registry = registry

    def run(self, name):
        plugin = self.registry.get(name)
        plugin.execute()
PY
python3 "$D" "$TMP/unresolved" --kind sequence --level 3 --entry "Worker.run" --no-mmdc >/tmp/dfc.out 2>&1
rc_is 0 $? "unresolved: diagrams a call through an untyped field"
has "%% unresolved"
grep -q "registry" /tmp/dfc.out && ok "unresolved: the unresolvable call site is still shown" \
  || bad "unresolved: the unresolvable call site was dropped"

# ---------- empty directory: clear message, not a traceback ----------
mkdir -p "$TMP/empty"
python3 "$D" "$TMP/empty" --kind sequence >/tmp/dfc.out 2>&1
rc=$?
[ "$rc" -eq 2 ] && ok "empty dir: exits 2 (not a crash)" || bad "empty dir: unexpected exit $rc"
grep -qi "traceback" /tmp/dfc.out && bad "empty dir: leaked a Python traceback" \
  || ok "empty dir: no traceback"
has "nothing to diagram"

# ---------- generated mermaid passes the syntax check ----------
for combo in "sequence 1" "sequence 2" "sequence 3" "deps 1" "deps 2" "deps 3"; do
  set -- $combo
  kind=$1; level=$2
  python3 "$D" "$ROOT/examples/login/src" --kind "$kind" --level "$level" --no-mmdc >/tmp/dfc.out 2>&1
  grep -q "syntax check (heuristic): OK" /tmp/dfc.out \
    && ok "syntax check passes: kind=$kind level=$level" \
    || bad "syntax check FAILED: kind=$kind level=$level"
done
python3 "$D" "$ROOT/examples/login/src" --kind flow --level 3 --entry "AuthService.login" --no-mmdc >/tmp/dfc.out 2>&1
grep -q "syntax check (heuristic): OK" /tmp/dfc.out && ok "syntax check passes: kind=flow level=3" \
  || bad "syntax check FAILED: kind=flow level=3"

# if mmdc/npx is reachable, also prove it against the real renderer (not just our heuristic)
if command -v npx >/dev/null 2>&1; then
  python3 "$D" "$ROOT/examples/login/src" --kind sequence --level 3 >/tmp/dfc.out 2>&1
  grep -q "syntax check (mmdc): OK" /tmp/dfc.out && ok "mermaid-cli confirms the diagram renders" \
    || bad "mermaid-cli did not confirm the diagram renders"
fi

# ---------- --entry not found is a clean usage error, not a crash ----------
python3 "$D" "$ROOT/examples/login/src" --kind sequence --entry "NoSuchClass.method" --no-mmdc >/tmp/dfc.out 2>&1
rc_is 2 $? "unknown --entry rejected cleanly"

echo
echo "diagram_from_code: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
