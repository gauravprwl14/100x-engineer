#!/usr/bin/env bash
# Regression suite for the verification gate. Run: bash tests/test_verification_gate.sh
# Exits non-zero on any failure, so it is CI-usable.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
git init -q; git config user.email t@t; git config user.name t
mkdir -p .claude scripts hooks
cp "$ROOT/hooks/verify_fingerprint.py" "$ROOT/hooks/require_verification.py" hooks/
cp "$ROOT/scripts/verified.py" scripts/
echo 'print("ok")' > pass_test.py
echo 'import sys; sys.exit(1)' > fail_test.py
echo 'x = 1' > app.py
# The gate is opt-in per project: a policy file is what activates it.
printf '{"required_checks":[]}\n' > .claude/verification-policy.json
git add -A; git commit -qm init

PASS=0; FAIL=0
check() { # check <expected> <label> <hookjson>
  local exp="$1" label="$2" payload="$3" got
  got=$(printf '%s' "$payload" | python3 hooks/require_verification.py \
        | python3 -c "import json,sys;print((json.load(sys.stdin).get('hookSpecificOutput') or {}).get('permissionDecision','passthrough'))")
  if [ "$got" = "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-52s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-52s expected=%s got=%s\n' "$label" "$exp" "$got"; fi
}
verify() { python3 scripts/verified.py --name "$1" -- python3 "$2" >/dev/null 2>&1 || true; }

C='{"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}'

check passthrough "unrelated bash command ignored" '{"tool_name":"Bash","tool_input":{"command":"ls"}}'
check passthrough "non-Bash tool ignored"          '{"tool_name":"Edit","tool_input":{"file_path":"a"}}'
check deny        "commit with no receipt"          "$C"
verify test pass_test.py
check allow       "commit with fresh passing check" "$C"
echo '# post-verification edit' >> app.py
check deny        "code edited after verification"  "$C"
verify test pass_test.py
check allow       "re-verified after edit"          "$C"
verify test fail_test.py
check deny        "failing check blocks"            "$C"
check allow       "explicit [skip-verify] bypass"   '{"tool_name":"Bash","tool_input":{"command":"git commit -m \"wip [skip-verify]\""}}'
# --no-verify is an EVASION signal, not a bypass grant: git skips its own hooks
# silently. Must be denied even though a fresh passing receipt exists.
check deny        "git commit --no-verify denied"   '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m x"}}'
check allow       "--no-verify + explicit skip ok"  '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m \"x [skip-verify]\""}}'
verify test pass_test.py
echo '{"required_checks":["test","typecheck"]}' > .claude/verification-policy.json
check deny        "policy: required check not run"  "$C"
verify typecheck pass_test.py
check allow       "policy: all required checks run" "$C"
printf '{"required_checks":[]}\n' > .claude/verification-policy.json
verify test pass_test.py
echo junk > agent_made_this.md
check deny        "new untracked file invalidates"  "$C"
rm agent_made_this.md; verify test pass_test.py
echo 'y = 2' > staged.py; git add staged.py
check deny        "staged-only change invalidates"  "$C"
rm -f staged.py; git reset -q; verify test pass_test.py
# With a fresh passing receipt, every completion action should be ALLOWED.
check allow       "gh pr create allowed when verified" '{"tool_name":"Bash","tool_input":{"command":"gh pr create --fill"}}'
check allow       "git push allowed when verified"     '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}'
check allow       "git tag allowed when verified"      '{"tool_name":"Bash","tool_input":{"command":"git tag v1.0.0"}}'
# Remove the receipt: the same actions must now be BLOCKED. This pair is the real
# assertion -- it proves the gate covers more than `git commit`.
rm -f .claude/verification-receipt.json
check deny        "gh pr create gated without receipt" '{"tool_name":"Bash","tool_input":{"command":"gh pr create --fill"}}'
check deny        "git push gated without receipt"     '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}'
check deny        "git tag gated without receipt"      '{"tool_name":"Bash","tool_input":{"command":"git tag v1.0.0"}}'
check deny        "npm publish gated without receipt"  '{"tool_name":"Bash","tool_input":{"command":"npm publish --access public"}}'

# A project that has NOT opted in must be untouched -- this is what keeps the
# user-scoped plugin from blocking commits in every unrelated repository.
rm -f .claude/verification-policy.json .claude/verification-receipt.json
check passthrough "no policy file => gate inactive"  "$C"
check passthrough "no policy => push untouched"      '{"tool_name":"Bash","tool_input":{"command":"git push"}}'
printf '{"required_checks":[]}\n' > .claude/verification-policy.json
check deny        "policy restored => gate active again" "$C"
printf 'not json\n' > .claude/verification-policy.json
check deny        "malformed policy fails closed"     "$C"

echo
echo "verification-gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
