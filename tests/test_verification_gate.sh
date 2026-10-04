#!/usr/bin/env bash
# Regression suite for the PreToolUse verification gate and the receipt writer.
# Run: bash tests/test_verification_gate.sh   Exits non-zero on any failure.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HUNDREDX_KEY_FILE="$TMP/key/receipt.key"
unset VERIFY_SKIP
HOOK="$ROOT/hooks/require_verification.py"
VERIFIED="$ROOT/scripts/verified.py"
R="$TMP/repo"; OTHER="$TMP/elsewhere"; mkdir -p "$R/.claude" "$OTHER"
cd "$R"
git init -q; git config user.email t@t; git config user.name t
echo 'print("ok")' > pass_test.py
echo 'import sys; sys.exit(1)' > fail_test.py
echo 'x = 1' > app.py
printf '{"required_checks": {"test": "python3 pass_test.py"}}\n' > .claude/verification-policy.json
printf '.claude/verification-receipt.json\n' > .gitignore
git add -A; git commit -qm init

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }

# run <payload-cwd> <command> : prints the hook's raw JSON. The hook process itself
# runs from $OTHER (not a repo) so every case also proves the payload cwd is used.
run() {
  python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":sys.argv[2]}}))' "$1" "$2" \
    | (cd "$OTHER" && python3 "$HOOK")
}
# kind <json> : deny | ask | allow | silent | message
kind() {
  printf '%s' "$1" | python3 -c '
import json,sys
d=json.load(sys.stdin); h=d.get("hookSpecificOutput") or {}
p=h.get("permissionDecision")
print(p if p else ("message" if d.get("systemMessage") else "silent"))'
}
# expect <kind> <label> <command> [payload-cwd] [grep-for-in-output]
expect() {
  local want="$1" label="$2" cmd="$3" cwd="${4:-$R}" pat="${5:-}" out got
  out="$(run "$cwd" "$cmd")"; got="$(kind "$out")"
  if [ "$got" = "$want" ] && { [ -z "$pat" ] || printf '%s' "$out" | grep -q -- "$pat"; }; then
    ok "$label"
  else
    bad "$label (want=$want${pat:+ containing '$pat'} got=$got)"; printf '       %s\n' "$out" | head -c 600; echo
  fi
}
verify() { (cd "$R" && python3 "$VERIFIED" --name "$1" -- "${@:2}" >/dev/null 2>&1); }
fresh()  { verify test python3 pass_test.py; }
C='git commit -m x'

echo "--- routing and passthrough"
expect silent "unrelated bash command ignored"      'ls -la'
expect silent "git status is not gated"             'git status'
expect silent "git tag -l is not gated"             'git tag -l'
expect silent "gh pr list is not gated"             'gh pr list'
expect silent "npm test is not gated"               'npm test'
expect silent "heredoc body is data, not a command" "$(printf 'cat > notes.txt <<EOF\ngit push origin main\nEOF')"
out="$(printf '%s' '{"tool_name":"Edit","tool_input":{"file_path":"a"}}' | python3 "$HOOK")"
[ "$(kind "$out")" = silent ] && ok "non-Bash tool ignored" || bad "non-Bash tool ignored"

echo "--- receipts"
expect deny   "commit with no receipt"              "$C" "$R" "no verification receipt"
fresh
expect message "commit with fresh signed receipt"   "$C" "$R" "PASSED"
out="$(run "$R" "$C")"; printf '%s' "$out" | grep -q '"allow"' \
  && bad "a passing gate must not emit allow (it would skip ask rules)" \
  || ok "a passing gate emits no allow decision"
[ "$(stat -f %Lp "$HUNDREDX_KEY_FILE" 2>/dev/null || stat -c %a "$HUNDREDX_KEY_FILE")" = 600 ] \
  && ok "signing key created with mode 0600" || bad "signing key created with mode 0600"

FP="$(cd "$R" && python3 "$ROOT/scripts/verify_fingerprint.py")"
python3 - "$FP" > .claude/verification-receipt.json <<'PY'
import json,sys
print(json.dumps({"version": 2, "checks": {"test": {"argv": ["python3", "pass_test.py"],
  "command": "python3 pass_test.py", "exit_code": 0, "fingerprint": sys.argv[1],
  "at": "2099-01-01T00:00:00+00:00", "duration_s": 0.1, "sig": "00" * 32}}}))
PY
expect deny   "forged receipt (hand-written, bad signature) denied" "$C" "$R" "signature"
python3 - "$FP" > .claude/verification-receipt.json <<'PY'
import json,sys
print(json.dumps({"version": 1, "checks": {"test": {"command": "python3 pass_test.py",
  "exit_code": 0, "fingerprint": sys.argv[1], "at": "2099-01-01T00:00:00+00:00"}}}))
PY
expect deny   "unsigned v1-style receipt denied"    "$C" "$R" "unsigned"
fresh
echo '# post-verification edit' >> app.py
expect deny   "code edited after verification"      "$C" "$R" "changed after verification"
NEWFP="$(cd "$R" && python3 "$ROOT/scripts/verify_fingerprint.py")"
python3 - "$NEWFP" <<'PY'
import json,sys
p=".claude/verification-receipt.json"; d=json.load(open(p))
d["checks"]["test"]["fingerprint"]=sys.argv[1]; json.dump(d,open(p,"w"))
PY
expect deny   "tampered receipt (fingerprint rewritten) denied" "$C" "$R" "signature"
fresh
expect message "re-verified after edit"             "$C"
cp "$HUNDREDX_KEY_FILE" "$TMP/key.bak"
printf '%s\n' "$(python3 -c 'print("ab"*32)')" > "$TMP/otherkey"; chmod 600 "$TMP/otherkey"
HUNDREDX_KEY_FILE="$TMP/otherkey" expect deny "receipt signed with another key denied" "$C" "$R" "signature"
chmod 644 "$HUNDREDX_KEY_FILE"
expect deny   "group/world-readable key refused"    "$C" "$R" "0600"
chmod 600 "$HUNDREDX_KEY_FILE"

echo "--- policy binds labels to commands"
(cd "$R" && python3 "$VERIFIED" --name test -- true >/dev/null 2>&1); rc=$?
[ "$rc" -eq 2 ] && ok "verified.py refuses a required label with another command" \
  || bad "verified.py refuses a required label with another command (rc=$rc)"
expect message "refused run left the real receipt intact" "$C"
(cd "$R" && python3 "$VERIFIED" --name test >/dev/null 2>&1) \
  && ok "--name alone runs the policy's command" || bad "--name alone runs the policy's command"
printf '{"required_checks": {"test": "python3 -c print(2)"}}\n' > .claude/verification-policy.json
git commit -qam "policy: change bound command"
expect deny   "receipt command differs from policy" "$C" "$R" "policy binds"
printf '{"required_checks": ["test"]}\n' > .claude/verification-policy.json
git commit -qam "policy: legacy list"
expect message "legacy list form: label-only + warning" "$C" "$R" "legacy list form"
printf '{"required_checks": {"test": "python3 pass_test.py", "typecheck": "python3 pass_test.py"}}\n' > .claude/verification-policy.json
git commit -qam "policy: two checks"
fresh
expect deny   "required check not run"              "$C" "$R" "typecheck"
verify typecheck python3 pass_test.py
expect message "all required checks run"            "$C"
verify extra python3 fail_test.py
expect deny   "a failing fresh check blocks"        "$C" "$R" "FAILED"
printf '{"required_checks": {"test": "python3 pass_test.py"}}\n' > .claude/verification-policy.json
git commit -qam "policy: one check"
rm .claude/verification-receipt.json; fresh

echo "--- worktree edits cannot weaken the committed policy"
printf '{"mode": "off"}\n' > .claude/verification-policy.json
echo 'x = 3' > app.py
expect deny   "uncommitted mode:off is not honoured" "$C" "$R" "committed policy"
mv .claude/verification-policy.json "$TMP/pol.bak"
expect deny   "deleting the policy file is not honoured" "$C" "$R" "committed policy"
mv "$TMP/pol.bak" .claude/verification-policy.json
git show HEAD:.claude/verification-policy.json > .claude/verification-policy.json
printf 'x = 1\n# post-verification edit\n' > app.py; fresh

echo "--- bypass and evasion"
expect ask    "[skip-verify] needs a human (ask)"   'git commit -m "wip [skip-verify]"' "$R" "WITHOUT"
expect deny   "git commit --no-verify denied"       'git commit --no-verify -m x'
expect deny   "git commit -n denied"                'git commit -n -m x'
expect deny   "short cluster -nm denied"            'git commit -nm x'
expect ask    "--no-verify + [skip-verify] asks"    'git commit --no-verify -m "x [skip-verify]"'
expect message "-m '-n' is a message, not a flag"   'git commit -m "-n"'
expect message "git log -n 3 && git commit not misflagged" 'git log -n 3 && git commit -m x'
expect deny   "-c core.hooksPath= is evasion"       'git -c core.hooksPath=/dev/null commit -m x'
expect deny   "git push --no-verify denied"         'git push --no-verify origin main'
git config alias.ci "commit -n"
expect deny   "alias expanding to commit -n denied" 'git ci -m x'
git config --unset alias.ci

echo "--- repository resolution"
expect message "git -C <repo> from a foreign cwd"   "git -C $R commit -m x" "$OTHER"
expect message "git -c k=v commit is recognised"    'git -c user.name=y commit -m x'
expect message "cd <repo> && git commit"            "cd $R && git commit -m x" "$OTHER"
expect message "--git-dir/--work-tree recognised"   "git --git-dir=$R/.git --work-tree=$R commit -m x" "$OTHER"
expect message "bash -c 'git commit' recognised"    "bash -c 'git commit -m x'"
expect message "foreign payload cwd resolved (hook runs elsewhere)" "$C" "$R"
mv .claude/verification-receipt.json "$TMP/receipt.bak"
expect deny   "git -C <repo> gated without receipt" "git -C $R commit -m x" "$OTHER"
expect deny   "git -c k=v commit gated"             'git -c user.name=y commit -m x'
expect deny   "cd <repo> && git commit gated"       "cd $R && git commit -m x" "$OTHER"
expect deny   "--git-dir commit gated"              "git --git-dir=$R/.git --work-tree=$R commit -m x" "$OTHER"
expect deny   "env/command wrappers gated"          'env FOO=1 command git commit -m x'
expect deny   "unbalanced quotes still gated"       'git commit -m "unterminated'
mv "$TMP/receipt.bak" .claude/verification-receipt.json

echo "--- every publish variant is routed by hooks.json and decided by the script"
PUBLISH=('git push origin main' 'git tag v1.0.0' 'git tag -a v1 -m rel' 'gh pr create --fill'
  'gh pr merge 3' 'gh release create v1.0.0' 'npm publish --access public' 'pnpm publish'
  'pnpm -r publish' 'yarn publish' 'yarn npm publish' 'twine upload dist/*'
  'python3 -m twine upload dist/*' 'uv publish' 'npm --registry https://r.example publish')
for c in "${PUBLISH[@]}"; do
  python3 - "$ROOT/hooks/hooks.json" "$c" <<'PY' && ok "hooks.json routes: $c" || bad "hooks.json routes: $c"
import fnmatch, json, sys
cfg = json.load(open(sys.argv[1]))
for group in cfg["hooks"]["PreToolUse"]:
    for h in group["hooks"]:
        pat = h.get("if", "")
        if pat.startswith("Bash(") and fnmatch.fnmatchcase(sys.argv[2], pat[5:-1]) \
           and "${CLAUDE_PLUGIN_ROOT}/hooks/require_verification.py" in h["command"]:
            sys.exit(0)
sys.exit(1)
PY
done
fresh
for c in "${PUBLISH[@]}"; do expect message "allowed when verified: $c" "$c"; done
mv .claude/verification-receipt.json "$TMP/receipt.bak"
for c in "${PUBLISH[@]}"; do expect deny "denied without receipt: $c" "$c"; done
mv "$TMP/receipt.bak" .claude/verification-receipt.json
expect silent "git push --dry-run is not gated"     'git push --dry-run'

echo "--- content fingerprint"
git add -A
expect message "staging verified content keeps the receipt" "$C"
git commit -qm "ship verified work"
expect message "commit then push allowed without rerun" 'git push origin main'
echo junk > agent_made_this.md
expect deny   "new untracked file invalidates"      "$C"
mv agent_made_this.md "$TMP/"; expect message "removing it restores the verified content" "$C"
echo 'y = 2' > staged.py; git add staged.py
expect deny   "newly staged file invalidates"       "$C"
git rm -q --cached staged.py; mv staged.py "$TMP/"
chmod +x app.py
expect deny   "mode change (chmod +x) invalidates"  "$C"
chmod -x app.py
echo '# unstaged' >> app.py; fresh
expect message "commit with unstaged verified edits warns" "$C" "$R" "never tested"

echo "--- unconfigured and disabled repositories"
mkdir -p "$OTHER/r2"; (cd "$OTHER/r2" && git init -q && git config user.email t@t && git config user.name t \
  && echo a > a && git add a && git commit -qm i)
expect message "no policy: allowed with a not-configured warning" "$C" "$OTHER/r2" "not configured"
expect message "no policy: --no-verify only warns"  'git commit --no-verify -m x' "$OTHER/r2" "not configured"
mkdir -p "$OTHER/r2/.claude"; printf '{"mode": "off"}\n' > "$OTHER/r2/.claude/verification-policy.json"
(cd "$OTHER/r2" && git add -A && git commit -qm off)
expect silent "mode off: silent"                    "$C" "$OTHER/r2"
printf '{"mode": "warn"}\n' > "$OTHER/r2/.claude/verification-policy.json"
(cd "$OTHER/r2" && git commit -qam bad)
expect deny   "unknown mode fails closed"           "$C" "$OTHER/r2" "invalid"
printf 'not json\n' > "$OTHER/r2/.claude/verification-policy.json"
(cd "$OTHER/r2" && git commit -qam bad2)
expect deny   "malformed policy fails closed"       "$C" "$OTHER/r2" "invalid"
expect silent "not a git repository: nothing to gate" "$C" "$OTHER"

echo "--- fail open"
printf 'not json at all' | python3 "$HOOK" >/dev/null 2>&1 && ok "malformed hook input exits 0" \
  || bad "malformed hook input exits 0"

echo
echo "verification-gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
