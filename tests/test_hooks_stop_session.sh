#!/usr/bin/env bash
# Regression suite for the Stop gate and the SessionStart context hook.
# Run: bash tests/test_hooks_stop_session.sh   Exits non-zero on any failure.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HUNDREDX_KEY_FILE="$TMP/key/receipt.key"
STOP="$ROOT/hooks/stop_gate.py"
SESSION="$ROOT/hooks/session_start.py"
R="$TMP/repo"; OTHER="$TMP/elsewhere"; mkdir -p "$R/.claude" "$OTHER"
cd "$R"
git init -q; git config user.email t@t; git config user.name t
echo 'print("ok")' > pass_test.py
echo 'x = 1' > app.py
printf '{"required_checks": {"test": "python3 pass_test.py"}}\n' > .claude/verification-policy.json
printf '.claude/verification-receipt.json\n' > .gitignore
git add -A; git commit -qm init

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }

# stop <payload-cwd> <stop_hook_active> : decision (block|none). The hook process
# runs from $OTHER so every case also proves the payload cwd is what gets judged.
stop() {
  python3 -c 'import json,sys; print(json.dumps({"hook_event_name":"Stop","session_id":"s","transcript_path":"/dev/null","cwd":sys.argv[1],"stop_hook_active":sys.argv[2]=="true"}))' "$1" "$2" \
    | (cd "$OTHER" && python3 "$STOP") | python3 -c 'import json,sys; print(json.load(sys.stdin).get("decision") or "none")'
}
expect() { # expect <want> <label> [cwd] [active]
  local got; got="$(stop "${3:-$R}" "${4:-false}")"
  [ "$got" = "$1" ] && ok "$2" || bad "$2 (want=$1 got=$got)"
}
fresh() { (cd "$R" && python3 "$ROOT/scripts/verified.py" --name test >/dev/null 2>&1); }

echo "--- Stop gate"
expect none  "clean tree: nothing unverified, stop allowed"
echo 'x = 2' > app.py
expect block "uncommitted change with no receipt blocks"
reason="$(python3 -c 'import json; print(json.dumps({"cwd":"'"$R"'","stop_hook_active":False}))' | python3 "$STOP")"
printf '%s' "$reason" | grep -q '100x verified --name test' && ok "block reason names the command to run" \
  || bad "block reason names the command to run"
fresh
expect none  "fresh receipt: stop allowed"
echo 'x = 3' > app.py
expect block "edit after verification (stale) blocks"
expect none  "stop_hook_active: never loops"         "$R" true
echo new > notes.md; fresh
expect none  "verified including a new file: allowed"
git add -A; git commit -qm work
expect none  "after committing verified work: allowed"
printf '{"mode": "off"}\n' > .claude/verification-policy.json; git commit -qam off
echo 'x = 4' > app.py
expect none  "mode off: never blocks"
mkdir -p "$OTHER/r2"; (cd "$OTHER/r2" && git init -q && echo a > a)
expect none  "no policy: never blocks"               "$OTHER/r2"
expect none  "not a git repository: never blocks"    "$OTHER"
printf 'garbage' | python3 "$STOP" > "$TMP/out" 2>&1; rc=$?
[ "$rc" -eq 0 ] && grep -q '^{}$' "$TMP/out" && ok "malformed input fails open" || bad "malformed input fails open"

echo "--- SessionStart"
out="$(printf '{"hook_event_name":"SessionStart","source":"startup","cwd":"%s"}' "$R" \
       | CLAUDE_PLUGIN_ROOT=/opt/plugin python3 "$SESSION")"
printf '%s' "$out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
h = d["hookSpecificOutput"]
assert h["hookEventName"] == "SessionStart", h
ctx = h["additionalContext"]
assert 0 < len(ctx.splitlines()) <= 10, len(ctx.splitlines())
for need in ("/100x-engineer:100x", "100x list", "/opt/plugin/docs/OPERATING-MODEL.md"):
    assert need in ctx, need
' && ok "SessionStart emits valid, short additionalContext" || bad "SessionStart JSON shape"
printf 'garbage' | python3 "$SESSION" >/dev/null 2>&1 && ok "SessionStart tolerates any stdin" \
  || bad "SessionStart tolerates any stdin"

echo "--- registration"
python3 - "$ROOT/hooks/hooks.json" <<'PY' && ok "Stop and SessionStart registered via CLAUDE_PLUGIN_ROOT" || bad "hook registration"
import json, sys
h = json.load(open(sys.argv[1]))["hooks"]
cmds = {ev: [x["command"] for g in h[ev] for x in g["hooks"]] for ev in ("Stop", "SessionStart")}
assert any("${CLAUDE_PLUGIN_ROOT}/hooks/stop_gate.py" in c for c in cmds["Stop"]), cmds
assert any("${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py" in c for c in cmds["SessionStart"]), cmds
PY

echo
echo "hooks-stop-session: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
