#!/usr/bin/env bash
# Regression suite for the PreToolUse verification gate and the receipt writer.
# Run: bash tests/test_verification_gate.sh   Exits non-zero on any failure.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HUNDREDX_KEY_FILE="$TMP/key/receipt.key"
unset VERIFY_SKIP PYTEST_ADDOPTS PYTEST_PLUGINS NODE_OPTIONS GOFLAGS LD_PRELOAD DYLD_INSERT_LIBRARIES
HOOK="$ROOT/hooks/require_verification.py"
VERIFIED="$ROOT/scripts/verified.py"
R="$TMP/repo"; OTHER="$TMP/elsewhere"; mkdir -p "$R/.claude" "$OTHER"
cd "$R"
git init -q; git config user.email t@t; git config user.name t
git symbolic-ref HEAD refs/heads/main     # independent of init.defaultBranch
echo 'print("ok")' > pass_test.py
echo 'import sys; sys.exit(1)' > fail_test.py
echo 'x = 1' > app.py
printf '{"required_checks": {"test": "python3 pass_test.py"}}\n' > .claude/verification-policy.json
git add -A; git commit -qm init
RCPT="$R/.git/100x/verification-receipt.json"    # `git rev-parse --git-path` in a plain repo

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
python3 - "$FP" > "$RCPT" <<'PY'
import json,sys
print(json.dumps({"version": 2, "checks": {"test": {"argv": ["python3", "pass_test.py"],
  "command": "python3 pass_test.py", "exit_code": 0, "fingerprint": sys.argv[1],
  "at": "2099-01-01T00:00:00+00:00", "duration_s": 0.1, "sig": "00" * 32}}}))
PY
expect deny   "forged receipt (hand-written, bad signature) denied" "$C" "$R" "signature"
python3 - "$FP" > "$RCPT" <<'PY'
import json,sys
print(json.dumps({"version": 1, "checks": {"test": {"command": "python3 pass_test.py",
  "exit_code": 0, "fingerprint": sys.argv[1], "at": "2099-01-01T00:00:00+00:00"}}}))
PY
expect deny   "unsigned v1-style receipt denied"    "$C" "$R" "unsigned"
fresh
echo '# post-verification edit' >> app.py
expect deny   "code edited after verification"      "$C" "$R" "changed after verification"
NEWFP="$(cd "$R" && python3 "$ROOT/scripts/verify_fingerprint.py")"
python3 - "$NEWFP" "$RCPT" <<'PY'
import json,sys
p=sys.argv[2]; d=json.load(open(p))
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
printf '\377\376%.0s' $(seq 32) > "$TMP/binkey"; chmod 600 "$TMP/binkey"
HUNDREDX_KEY_FILE="$TMP/binkey" expect deny "non-UTF-8 key is malformed, not a fail-open" "$C" "$R" "malformed"

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
rm "$RCPT"; fresh

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
mv "$RCPT" "$TMP/receipt.bak"
expect deny   "git -C <repo> gated without receipt" "git -C $R commit -m x" "$OTHER"
expect deny   "git -c k=v commit gated"             'git -c user.name=y commit -m x'
expect deny   "cd <repo> && git commit gated"       "cd $R && git commit -m x" "$OTHER"
expect deny   "--git-dir commit gated"              "git --git-dir=$R/.git --work-tree=$R commit -m x" "$OTHER"
expect deny   "env/command wrappers gated"          'env FOO=1 command git commit -m x'
expect deny   "unbalanced quotes still gated"       'git commit -m "unterminated'

echo "--- every natural phrasing reaches a decision (no receipt: denied)"
REGRESS=('timeout 60 git commit -am x' 'timeout -s KILL 60 git commit -m x'
  'nice -n 5 git commit -m x' 'eval git commit -m x' 'eval "git commit -m x"'
  'echo x | xargs git commit -m' 'xargs -I{} git commit -m {} < /dev/null'
  'cd "$PWD" && git commit -m x' 'git -C "$PWD" commit -m x' '{ git push; }'
  'if true; then git push; fi' 'for i in 1; do git push; done'
  'while false; do :; done; until git push; do :; done' '! git commit -m x'
  'env -u FOO git push' 'env -S "git commit -m x"' 'sudo -u me git push'
  'doas -u me git push' 'stdbuf -oL git commit -m x' 'watch -n 5 git push'
  'find . -exec git commit -m x \;' 'docker run img git push'
  'G=git; $G commit -m x' '$(echo git) commit -m x' '`echo git` commit -m x'
  'X=$(echo git); $X push' '$UNSET_PROGRAM commit -m x'
  'git -c alias.ci=commit ci -m x'
  'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.ci GIT_CONFIG_VALUE_0=commit git ci -m x'
  "export GIT_DIR=$R/.git; git commit -m x"
  "export GIT_DIR=$R/.git GIT_WORK_TREE=$R; cd $OTHER; git commit -m x"
  '(cd /); git commit -m x' 'bash -c "cd /"; git commit -m x'
  'git commit-tree HEAD^{tree} -m x' 'git update-ref refs/heads/main HEAD'
  'git send-pack origin main' 'git merge feature' 'git merge --continue'
  'gh pr merge 3' 'gh api repos/o/r/pulls/1/merge -X PUT'
  'echo "git push origin main" | bash' 'git commit -m "$(cat msg.txt)"'
  "$(printf 'bash <<EOF\ngit commit -m x\nEOF')"
  "$(printf 'cat <<EOF\n$(git push)\nEOF')")
for c in "${REGRESS[@]}"; do expect deny "gated: ${c//$'\n'/ | }" "$c"; done
expect deny   "an abbreviated long option is still the evasion" 'git commit --no-veri -m x' "$R" "skips git"
expect deny   "core.hooksPath via GIT_CONFIG_* is evasion" \
  'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x' "$R" "hooks"

echo "--- review repros: each of these reached no decision before (no receipt: denied)"
NL=$'\n'
REVIEW=('echo issue#12 && git commit -m x' 'echo ${#PATH} && git commit -m x'
  'curl -s https://example.com/page#top >/dev/null; git push origin main'
  '[ $# -eq 0 ] && git commit -am x' 'open http://localhost:3000/#/home && git push'
  "git -C . \\${NL}commit -am x" "git -c user.name=x \\${NL}push origin main" "gh \\${NL}pr merge 1"
  "echo \"a <<EOF\"${NL}git commit -m x" "echo \$((a<<b))${NL}git commit -m x"
  "git commit -m \"use <<EOF heredocs\"${NL}git push origin HEAD" "echo \"a<<EOF\"${NL}git commit -am x"
  "cat <<EOF-X${NL}EOF-X${NL}git commit -am x${NL}EOF"
  "bash -o pipefail -c 'git commit -am x'" "bash -euo pipefail -c 'git commit -am x'"
  "bash -O extglob -c 'git commit -am x'" "sh +o nounset -c 'git push'"
  'poetry publish' 'hatch publish' 'cargo publish' 'cargo +nightly publish' 'gem push x.gem'
  'mytool publish' 'git ${C:-commit} -m x' "git \$'commit' -m x" 'git "$(echo commit)" -m x'
  'git $(echo commit) -am x' 'git ${S:-commit} -m x' "git co\$'mmit' -m x"
  'pnpm exec git commit -am x' 'npm exec -- git commit -m x' 'uv run git commit -m x'
  'yarn dlx git push' 'source <(echo git commit -am x)' '. <(echo git push)'
  'git config alias.ci commit && git ci -m x')
for c in "${REVIEW[@]}"; do expect deny "gated: ${c//$'\n'/ | }" "$c"; done
if [ "$(uname)" = Darwin ]; then
  expect deny "case-insensitive filesystem: GIT commit" 'GIT commit -am x'
  expect deny "case-insensitive filesystem: Git push"   'Git push origin main'
fi

echo "--- no false positives on look-alikes"
QUIET=('echo git commit' 'printf "%s\n" "git push origin main"' 'grep -rn "git push" .'
  'git log --grep commit' 'ls .github' 'echo $(git rev-parse HEAD)' 'cat <<< "git push"'
  'git merge --abort' 'git update-ref -d refs/heads/x' 'gh api repos/o/r/pulls'
  'command -v git' 'man git-push' 'git push -n origin main' 'npm run build'
  'for f in commit push; do echo $f; done' 'git config alias.ci' 'brew install git gh'
  "$(printf 'cat > n.md <<EOF\n$ git push origin main\nEOF')"
  'ls # git commit -m x' 'echo hi   # then git push' "$(printf 'ls\n# git push origin main')"
  'echo "a#b git commit"' "git status \\${NL}--short" "bash -o pipefail -c 'echo hi'"
  'npm exec -- prettier --check .' 'uv run pytest' 'cargo build' 'poetry install' 'gem list'
  'echo publish' 'git config alias.ci commit' "$(printf "cat <<'EOF'\ngit push\nEOF")"
  "$(printf 'cat <<EOF-X\ngit push\nEOF-X')" 'echo $((1<<3))')
for c in "${QUIET[@]}"; do expect silent "not gated: ${c//$'\n'/ | }" "$c"; done
mv "$TMP/receipt.bak" "$RCPT"

echo "--- parsed as the real command, not just matched (fresh receipt: passes)"
git add -A; git commit -qm "pre-regression state" >/dev/null 2>&1; fresh
PASSING=('timeout 60 git commit -am x' 'nice -n 5 git commit -m x' 'eval git commit -m x'
  'echo x | xargs git commit -m' 'cd "$PWD" && git commit -m x' 'git -C "$PWD" commit -m x'
  '{ git push; }' 'if true; then git push; fi' 'for i in 1; do git push; done'
  'env -u FOO git push' 'sudo -u me git push' 'G=git; $G commit -m x'
  'git -c alias.ci=commit ci -m x' "export GIT_DIR=$R/.git; git commit -m x"
  'git status && git commit -m x' 'git add -A && git commit -m x'
  'git diff --stat; git commit -m x 2>/dev/null'
  'cd "$(git rev-parse --show-toplevel)" && git commit -m x')
for c in "${PASSING[@]}"; do expect message "passes when verified: $c" "$c" "$R" "PASSED"; done

echo "--- B1: an edit chained before the commit is refused (fresh receipt)"
T='separate command'
expect deny   "append then commit -am"             'echo evil >> app.py && git commit -am x' "$R" "$T"
expect deny   "sed; add; commit"                   "sed -i.bak s/x/y/ app.py; git add app.py; git commit -m y" "$R" "$T"
expect deny   "test run then commit"               'python3 pass_test.py && git commit -m x' "$R" "$T"
expect deny   "edit inside bash -c before commit"  "bash -c 'echo evil > app.py; git commit -am x'" "$R" "$T"
expect deny   "edit in a substitution"             'git commit -m "$(echo evil > app.py)"' "$R" "$T"
expect deny   "edit before push"                   'echo evil >> app.py; git push' "$R" "$T"
expect message "redirect to /dev/null is not an edit" 'echo x > /dev/null && git commit -m x' "$R" "PASSED"
expect deny   "git diff --output writes a file"    'git diff --output=a.txt && git commit -am x' "$R" "$T"
expect deny   "git log --output writes a file"     'git log --output a.txt && git commit -am x' "$R" "$T"
expect deny   "-c config on a read-only git can run code" "git -c core.fsmonitor='touch zz' status && git commit -m x" "$R" "$T"
expect deny   "-c filter on git add can run code"  "git -c filter.x.clean='touch zz' add . && git commit -m x" "$R" "$T"
expect message "plain git diff is still read-only" 'git diff && git commit -m x' "$R" "PASSED"

echo "--- every publish variant is routed by hooks.json and decided by the script"
PUBLISH=('git push origin main' 'git tag v1.0.0' 'git tag -a v1 -m rel' 'gh pr create --fill'
  'gh pr merge 3' 'gh release create v1.0.0' 'npm publish --access public' 'pnpm publish'
  'pnpm -r publish' 'yarn publish' 'yarn npm publish' 'twine upload dist/*'
  'python3 -m twine upload dist/*' 'uv publish' 'npm --registry https://r.example publish')
ROUTED=("${PUBLISH[@]}" '$(echo git) commit -m x' 'G=git; $G commit' 'timeout 60 git commit -am x'
  'X=$(printf g)it; $X push' 'gh api repos/o/r/pulls/1/merge -X PUT')
for c in "${ROUTED[@]}"; do
  python3 - "$ROOT/hooks/hooks.json" "$c" <<'PY'&& ok "hooks.json routes: $c" || bad "hooks.json routes: $c"
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
mv "$RCPT" "$TMP/receipt.bak"
for c in "${PUBLISH[@]}"; do expect deny "denied without receipt: $c" "$c"; done
mv "$TMP/receipt.bak" "$RCPT"
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

echo "--- S4: a push is bound to what it sends, not the working tree"
git add -A; git commit -qm "push binding base" >/dev/null 2>&1; fresh
BADC="$(git commit-tree "HEAD^{tree}" -p HEAD -m bad)"; git update-ref refs/heads/bad "$BADC"
git tag old-release "$BADC"
expect message "push current branch"                'git push origin main' "$R" "PASSED"
expect message "push HEAD:main"                     'git push origin HEAD:main' "$R" "PASSED"
expect message "bare git push"                      'git push' "$R" "PASSED"
expect message "deleting a remote ref sends nothing" 'git push origin :old' "$R" "PASSED"
expect deny   "push another branch"                 'git push origin bad' "$R" "not the checked-out"
expect deny   "push bad:main"                       'git push origin bad:main' "$R" "not the checked-out"
expect deny   "push +bad:main"                      'git push -f origin +bad:main' "$R" "not the checked-out"
expect deny   "push --tags with a tag elsewhere"    'git push --tags' "$R" "old-release"
expect deny   "push --all with another branch"      'git push --all origin' "$R" "bad"
expect deny   "push origin : (matching) sends every branch" 'git push origin :' "$R" "bad"
expect deny   "-c push.default=matching widens a plain push" 'git -c push.default=matching push origin' "$R" "bad"
expect deny   "-c remote.origin.mirror=true is a mirror push" 'git -c remote.origin.mirror=true push origin' "$R" "old-release"
expect deny   "-c remote.origin.push refspecs: refs unknown" 'git -c remote.origin.push=bad:main push origin' "$R" "cannot tell"
git config push.default matching
expect deny   "push.default=matching from repo config" 'git push origin' "$R" "bad"
git config --unset push.default
git remote add origin "$TMP/nowhere.git"; git config remote.origin.mirror true
expect deny   "remote.origin.mirror from repo config" 'git push' "$R" "old-release"
git remote remove origin
expect message "push.default=simple is not widened" 'git -c push.default=simple push origin main' "$R" "PASSED"
expect deny   "push an unknown ref"                 'git push origin nosuch' "$R" "local commit"
expect deny   "gh pr create --head bad"             'gh pr create --head bad --fill' "$R" "not the checked-out"
expect deny   "unresolvable program pushing bad"    '$(echo git) push origin bad' "$R" "not the checked-out"
expect deny   "push through a bare shell: refs unknown" 'echo "git push origin main" | sh' "$R" "cannot tell"
git tag good-release; expect message "push a tag at HEAD" 'git push origin good-release' "$R" "PASSED"
echo 'x = 9' > app.py; fresh
expect deny   "uncommitted verified edits: push denied" 'git push origin main' "$R" "uncommitted"
expect deny   "uncommitted verified edits: gh pr create denied" 'gh pr create --fill' "$R" "uncommitted"
expect deny   "commit -am && push: the commit has not happened yet" 'git commit -am x && git push' "$R" "separate command"
expect deny   "commit (not -a) && push would send less" 'git commit -m x && git push' "$R" "separate command"
expect deny   "pathspec commit && push"            'git commit -m x b.txt && git push origin main' "$R" "separate command"
expect deny   "commit; push"                       'git commit -m x; git push origin main' "$R" "separate command"
expect deny   "GIT_INDEX_FILE commit && push"      'GIT_INDEX_FILE=/tmp/nope git commit -m x && git push origin main' "$R" "separate command"
expect deny   "commit && gh pr create"             'git commit -am x && gh pr create --fill' "$R" "separate command"
git commit -qam "app 9"; fresh

echo "--- P5: a commit that changes the policy needs a receipt taken with it"
printf '{"required_checks": {"test": "python3 pass_test.py"}, "max_age_minutes": 9999}\n' > .claude/verification-policy.json
git add .claude/verification-policy.json
expect deny   "staged policy edit rides an old receipt" "$C" "$R" "changes .claude/verification-policy.json"
expect deny   "commit -a with a policy edit"        'git commit -am x' "$R" "changes .claude"
fresh
expect message "re-verified with the new policy in place" "$C" "$R" "PASSED"
git commit -qm "policy: max age"; fresh
expect message "no policy change: old receipts still fine" "$C" "$R" "PASSED"
printf '{"mode": "off"}\n' > .claude/verification-policy.json
expect message "unstaged policy edit, plain commit: the policy is not committed" "$C" "$R" "PASSED"
expect deny   "git add -A && commit weakens the policy" 'git add -A && git commit -m weaken' "$R" "changes .claude/verification-policy.json"
expect deny   "git add .claude && commit weakens the policy" 'git add .claude && git commit -m weaken' "$R" "changes .claude"
git show HEAD:.claude/verification-policy.json > .claude/verification-policy.json

echo "--- B2: the receipt write cannot be redirected by a symlink"
mkdir -p "$TMP/outside"; echo precious > "$TMP/victim.txt"
B="$TMP/b2"; mkdir -p "$B"; (cd "$B" && git init -q && git config user.email t@t && git config user.name t \
  && echo a > a && git add a && git commit -qm i)
mkdir -p "$B/.git/100x"; ln -s "$TMP/victim.txt" "$B/.git/100x/verification-receipt.json"
(cd "$B" && python3 "$VERIFIED" --name t -- true >/dev/null 2>"$TMP/err"); rc=$?
[ "$rc" -eq 2 ] && grep -q symlink "$TMP/err" && [ "$(cat "$TMP/victim.txt")" = precious ] \
  && ok "receipt symlink refused (exit 2)" || bad "receipt symlink refused (rc=$rc)"
rm -rf "$B/.git/100x"; ln -s "$TMP/outside" "$B/.git/100x"
(cd "$B" && python3 "$VERIFIED" --name t -- true >/dev/null 2>"$TMP/err"); rc=$?
[ "$rc" -eq 2 ] && grep -q symlink "$TMP/err" && [ -z "$(ls -A "$TMP/outside")" ] \
  && ok "git-dir 100x/ symlinked outside refused (exit 2)" || bad "100x/ symlink refused (rc=$rc)"
mkdir -p "$B/.claude"; printf '{"required_checks": {"t": "true"}}\n' > "$B/.claude/verification-policy.json"
(cd "$B" && git add -A && git commit -qm pol)
expect deny   "hook refuses a symlinked 100x/ dir"  "$C" "$B" "symlink"
rm "$B/.git/100x"
(cd "$B" && python3 "$VERIFIED" --name t >/dev/null 2>&1) && [ -f "$B/.git/100x/verification-receipt.json" ] \
  && ok "a real 100x/ dir is created on the next run" || bad "a real 100x/ dir is created on the next run"

echo "--- R1: the receipt lives in the git directory, never in the worktree"
[ -z "$(cd "$B" && git status --porcelain --untracked-files=all)" ] \
  && ok "plain repo: git status is empty after verified" || bad "plain repo: git status shows $(cd "$B" && git status --porcelain)"
[ ! -e "$B/.claude/verification-receipt.json" ] && ok "no receipt written under .claude/" \
  || bad "no receipt written under .claude/"
[ "$(cd "$B" && git rev-parse --git-path 100x/verification-receipt.json)" = .git/100x/verification-receipt.json ] \
  && ok "plain repo: receipt is at git rev-parse --git-path" || bad "plain repo: git-path location"
expect message "plain repo: gate allows after verify" "$C" "$B" "PASSED"
echo b > "$B/a"
expect deny   "plain repo: gate denies after an edit" "$C" "$B" "changed after verification"
(cd "$B" && git checkout -q -- a)
W="$TMP/b2-linked"; (cd "$B" && git worktree add -q -b linked "$W" >/dev/null 2>&1)
WGP="$(cd "$W" && git rev-parse --git-path 100x/verification-receipt.json)"
case "$WGP" in /*) ;; *) WGP="$W/$WGP" ;; esac
expect deny   "linked worktree: no receipt of its own is denied" "$C" "$W" "no verification receipt"
(cd "$W" && python3 "$VERIFIED" --name t >/dev/null 2>&1)
[ -f "$WGP" ] && [ "$(cd "$W" && git rev-parse --absolute-git-dir)/100x/verification-receipt.json" = "$WGP" ] \
  && ok "linked worktree: receipt lands in its own .git/worktrees/<name>/" || bad "linked worktree: receipt at $WGP"
[ -z "$(cd "$W" && git status --porcelain --untracked-files=all)" ] \
  && ok "linked worktree: git status is empty after verified" || bad "linked worktree: git status not empty"
expect message "linked worktree: gate allows after verify" "$C" "$W" "PASSED"
echo c > "$W/a"
expect deny   "linked worktree: gate denies after an edit" "$C" "$W" "changed after verification"
expect message "main worktree keeps its own receipt"   "$C" "$B" "PASSED"
(cd "$W" && python3 "$VERIFIED" --name t >/dev/null 2>&1)
expect message "linked worktree: re-verified after the edit" "$C" "$W" "PASSED"
mkdir -p "$B/.claude"; echo '{"version": 2, "checks": {}}' > "$B/.claude/verification-receipt.json"
(cd "$B" && python3 "$VERIFIED" --name t 2>"$TMP/err" >/dev/null)
grep -q "verification-receipt.json is from an older version and is ignored" "$TMP/err" \
  && ok "legacy .claude receipt: verified prints a note" || bad "legacy .claude receipt: verified prints a note"
[ "$(grep -c "older version" "$TMP/err")" = 1 ] && [ -f "$B/.claude/verification-receipt.json" ] \
  && ok "legacy receipt: one line, and it is not deleted" || bad "legacy receipt: one line, and it is not deleted"
expect message "legacy receipt: gate reads the git-dir receipt, with a note" "$C" "$B" "older version"
cp "$WGP" "$TMP/linked.keep"; mv "$WGP" "$TMP/linked.bak"
mkdir -p "$W/.claude"; cp "$TMP/linked.keep" "$W/.claude/verification-receipt.json"
expect deny   "a valid receipt at the legacy path is not honoured" "$C" "$W" "no verification receipt"
mv "$TMP/linked.bak" "$WGP"

echo "--- S3: runner-altering environment and PATH shadowing are refused"
cp "$RCPT" "$TMP/receipt.keep"
for v in PYTEST_ADDOPTS NODE_OPTIONS GOFLAGS BASH_ENV ENV npm_config_script_shell NPM_CONFIG_SCRIPT_SHELL; do
  (cd "$R" && env "$v=--x" python3 "$VERIFIED" --name test >/dev/null 2>"$TMP/err"); rc=$?
  [ "$rc" -eq 2 ] && grep -q "$v" "$TMP/err" && ok "$v set: refused (exit 2)" || bad "$v set: refused (rc=$rc)"
done
cmp -s "$RCPT" "$TMP/receipt.keep" && ok "refusals leave the receipt untouched" \
  || bad "refusals leave the receipt untouched"
PYBIN="$(command -v python3)"   # the gate's own interpreter, not the planted one
mkdir -p "$TMP/evil"; printf '#!/bin/sh\nexit 0\n' > "$TMP/evil/python3"; chmod +x "$TMP/evil/python3"
(cd "$R" && PATH="$TMP/evil:$PATH" "$PYBIN" "$VERIFIED" --name test >/dev/null 2>"$TMP/err"); rc=$?
[ "$rc" -eq 2 ] && grep -q "inside" "$TMP/err" && ok "python3 shadowed from a temp dir: refused" \
  || bad "python3 shadowed from a temp dir: refused (rc=$rc)"
mkdir -p "$R/bin"; cp "$TMP/evil/python3" "$R/bin/python3"
(cd "$R" && PATH="$R/bin:$PATH" "$PYBIN" "$VERIFIED" --name test >/dev/null 2>"$TMP/err"); rc=$?
[ "$rc" -eq 2 ] && grep -q "repository" "$TMP/err" && ok "python3 shadowed from inside the repo: refused" \
  || bad "python3 shadowed from inside the repo: refused (rc=$rc)"
rm -rf "$R/bin"
mkdir -p "$TMP/x/node_modules/.bin"; cp "$TMP/evil/python3" "$TMP/x/node_modules/.bin/python3"
(cd "$R" && PATH="$TMP/x/node_modules/.bin:$PATH" "$PYBIN" "$VERIFIED" --name test >/dev/null 2>"$TMP/err"); rc=$?
[ "$rc" -eq 2 ] && grep -q "inside" "$TMP/err" && ok "a temp dir named node_modules/.bin is not exempt" \
  || bad "a temp dir named node_modules/.bin is not exempt (rc=$rc)"
mkdir -p "$TMP/venv/bin"; touch "$TMP/venv/pyvenv.cfg"; cp "$TMP/evil/python3" "$TMP/venv/bin/python3"
(cd "$R" && PATH="$TMP/venv/bin:$PATH" "$PYBIN" "$VERIFIED" --name test >/dev/null 2>"$TMP/err"); rc=$?
[ "$rc" -eq 2 ] && grep -q "inside" "$TMP/err" && ok "a temp dir beside a fake pyvenv.cfg is not exempt" \
  || bad "a temp dir beside a fake pyvenv.cfg is not exempt (rc=$rc)"
printf '#!/usr/bin/env python3\nimport sys; sys.exit(1)\n' > "$R/check.sh"; chmod +x "$R/check.sh"
(cd "$R" && PATH="$TMP/evil:$PATH" "$PYBIN" "$VERIFIED" --name shebang -- ./check.sh >/dev/null 2>"$TMP/err"); rc=$?
[ "$rc" -eq 2 ] && grep -q "python3" "$TMP/err" && grep -q "inside" "$TMP/err" \
  && ok "a fake interpreter for an env shebang is refused" || bad "a fake interpreter for an env shebang is refused (rc=$rc)"
rm "$R/check.sh"
REALPY="$(python3 -c 'import os,shutil; print(os.path.realpath(shutil.which("python3")))')"
mkdir -p "$TMP/link"; ln -s "$REALPY" "$TMP/link/python3"
(cd "$R" && PATH="$TMP/link:$PATH" python3 "$VERIFIED" --name test >/dev/null 2>&1) \
  && ok "a temp-dir symlink to the real python3 is accepted" || bad "a temp-dir symlink to the real python3 is accepted"
mkdir -p "$R/node_modules/.bin"; printf '#!/bin/sh\nexec "%s" "$@"\n' "$REALPY" > "$R/node_modules/.bin/python3"
chmod +x "$R/node_modules/.bin/python3"
(cd "$R" && PATH="$R/node_modules/.bin:$PATH" "$PYBIN" "$VERIFIED" --name test >/dev/null 2>&1) \
  && ok "the repository's own node_modules/.bin stays exempt" || bad "the repository's own node_modules/.bin stays exempt"
rm -rf "$R/node_modules"
(cd "$R" && python3 "$VERIFIED" --name test >/dev/null 2>&1)
python3 - "$REALPY" "$RCPT" <<'PY' && ok "receipt records the executable's real path" || bad "receipt records the executable's real path"
import json, sys
e = json.load(open(sys.argv[2]))["checks"]["test"]
import os
home = os.path.realpath(os.path.expanduser("~"))
want = "~" + sys.argv[1][len(home):] if sys.argv[1].startswith(home + os.sep) else sys.argv[1]
assert e.get("exe") == want, (e.get("exe"), want)
PY

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

echo "--- writing and scope warnings (advisory, never change the decision)"
# has <label> <output> <pattern> / lacks <label> <output> <pattern>
has()   { printf '%s' "$2" | grep -q -- "$3" && ok "$1" || { bad "$1 (missing '$3')"; printf '       %s\n' "$2" | head -c 600; echo; }; }
lacks() { printf '%s' "$2" | grep -q -- "$3" && { bad "$1 (unexpected '$3')"; printf '       %s\n' "$2" | head -c 600; echo; } || ok "$1"; }
W="$OTHER/r3"; mkdir -p "$W/app/reactions" "$W/app/tagging"
(cd "$W" && git init -q && git config user.email t@t && git config user.name t \
  && git symbolic-ref HEAD refs/heads/main && echo a > app/reactions/a.rb && echo a > app/tagging/t.rb \
  && git add -A && git commit -qm i && git checkout -qb feat/reactions \
  && echo b >> app/reactions/a.rb && echo b >> app/tagging/t.rb && git commit -qam r)
SLOP='This PR adds reactions.
- [x] Tested
- [x] Verified everything works'
CLEAN='Closes #12

Add reaction counts to posts, from one grouped query per page.'
q() { python3 -c 'import shlex,sys; print(shlex.quote(sys.argv[1]))' "$1"; }
out="$(run "$W" "gh pr create --base main --title t --body $(q "$SLOP")")"
[ "$(kind "$out")" = message ] && ok "slop PR body: still allowed (no decision)" || bad "slop PR body: still allowed (got $(kind "$out"))"
has   "slop PR body: warnings reach the agent as context" "$out" "additionalContext.*self-ticked-box"
has   "slop PR body: the not-configured notice is kept"   "$out" "not configured"
out="$(run "$W" "gh pr create --base main --title t --body $(q "$CLEAN")")"
lacks "clean PR body: no writing warnings" "$out" "Writing and scope check"
out="$(run "$W" "gh pr create --base main --title t --body $(q "$CLEAN

scope: app/reactions/**")")"
has   "gh pr create: file outside the body's scope is flagged" "$out" "out-of-scope.*app/tagging/t.rb"
lacks "gh pr create: in-scope file is not flagged" "$out" "app/reactions/a.rb:"
printf '%s\n' "$SLOP" > "$TMP/body.md"
out="$(run "$W" "gh pr edit 3 --body-file $TMP/body.md")"
[ "$(kind "$out")" = message ] && has "gh pr edit --body-file: checked, not gated" "$out" "claim-without-evidence" \
  || bad "gh pr edit --body-file: checked, not gated (got $(kind "$out"))"
out="$(run "$W" 'git commit -m "This commit adds reactions. Verified it works."')"
has   "commit -m: message checked"  "$out" "\[commit\]\|commit line"
out="$(run "$W" "$(printf 'git commit -m "$(cat <<'"'"'EOF'"'"'\nAdd reactions\n\nThis PR adds reactions.\nEOF\n)"')")"
has   "commit -m \"\$(cat <<EOF)\": heredoc message checked" "$out" "filler-phrase"
out="$(run "$W" 'git commit -m "Add reaction counts to posts"')"
lacks "clean commit message: no warnings" "$out" "Writing and scope check"
N=13; LINES=""; for i in $(seq $N); do LINES="$LINES
- [x] Tested part $i"; done
out="$(run "$W" "gh pr edit 3 --body $(q "$LINES")")"
has   "findings capped at 8 plus a count" "$out" "more: run"
[ "$(printf '%s' "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["systemMessage"].count("\n  - "))')" = 8 ] \
  && ok "exactly 8 findings shown" || bad "exactly 8 findings shown"
P="$TMP/plug"; mkdir -p "$P"; cp -R "$ROOT/hooks" "$ROOT/scripts" "$P/"; rm -f "$P/scripts/prose_check.py"
rm -rf "$P/scripts/__pycache__"
out="$(python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","cwd":sys.argv[1],"tool_input":{"command":sys.argv[2]}}))' \
  "$W" "gh pr create --base main --title t --body $(q "$SLOP")" | (cd "$OTHER" && python3 "$P/hooks/require_verification.py"))"; rc=$?
[ "$rc" -eq 0 ] && [ "$(kind "$out")" = message ] && ok "prose_check absent: fail-open, still allowed" \
  || bad "prose_check absent: fail-open, still allowed (rc=$rc got $(kind "$out"))"
lacks "prose_check absent: no crash reported" "$out" "hook error"
lacks "prose_check absent: the copy without it was the one run" "$out" "self-ticked-box"
G="$OTHER/r4"; mkdir -p "$G/.claude"
(cd "$G" && git init -q && git config user.email t@t && git config user.name t \
  && echo 'print("ok")' > pass_test.py \
  && printf '{"required_checks": {"test": "python3 pass_test.py"}}\n' > .claude/verification-policy.json \
  && git add -A && git commit -qm i)
out="$(run "$G" "gh pr create --title t --body $(q "$SLOP")")"
[ "$(kind "$out")" = deny ] && ok "policy + no receipt: slop PR still blocked" || bad "policy + no receipt: slop PR still blocked (got $(kind "$out"))"
has   "policy + no receipt: the deny reason is unchanged" "$out" "no verification receipt"
lacks "policy + no receipt: no warnings mixed into a deny" "$out" "Writing and scope check"
(cd "$G" && python3 "$VERIFIED" --name test >/dev/null 2>&1)
out="$(run "$G" 'git commit -m "This commit adds reactions. Verified it works."')"
has   "policy + fresh receipt: commit passes" "$out" "PASSED"
has   "policy + fresh receipt: writing warnings appended" "$out" "Writing and scope check"

echo "--- fail open"
printf 'not json at all' | python3 "$HOOK" >/dev/null 2>&1 && ok "malformed hook input exits 0" \
  || bad "malformed hook input exits 0"

echo
echo "verification-gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
