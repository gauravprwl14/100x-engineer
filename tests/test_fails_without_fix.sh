#!/usr/bin/env bash
# Regression suite for fails_without_fix.py. Detection: a weak test that passes with the
# fix reverted, no test changes, and tests already red on HEAD are each reported. No false
# positive: a test that does exercise the fix is "ok". Safety: the user's working tree,
# index and stash are byte-identical afterwards and no worktree is left behind.
# Run: bash tests/test_fails_without_fix.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOL="$ROOT/scripts/fails_without_fix.py"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
OUT="$TMP/out"
# The tool's temp dirs land here, so "none left behind" is checkable in isolation.
export TMPDIR="$TMP/tmpdir"; mkdir -p "$TMPDIR"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-64s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "$1"; sed 's/^/       /' "$OUT" | tail -12; }

# A repo whose main branch has a bug in calc.add; the caller adds the branch commit.
new_repo() {
  local dir="$TMP/$1"
  mkdir -p "$dir/tests" && cd "$dir" || exit 1
  git init -q -b main; git config user.email t@t; git config user.name t
  printf 'def add(a, b):\n    return a - b\n' > calc.py
  : > tests/__init__.py
  git add -A; git commit -qm base
  git checkout -qb fix
}
fix_bug() { printf 'def add(a, b):\n    return a + b\n' > calc.py; }
write_test() { # write_test <assertion line>
  printf 'import unittest\nimport calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        %s\n' "$1" > tests/test_calc.py
}
commit_all() { git add -A; git commit -qm "$1"; }
run() { python3 "$TOOL" --base main --test-cmd "python3 -m unittest" "$@" >"$OUT" 2>&1; echo $?; }
expect() { # expect <exit> <regex> <label> [tool args...]
  local want="$1" rx="$2" label="$3"; shift 3
  local got; got="$(run "$@")"
  if [ "$got" = "$want" ] && grep -qE -- "$rx" "$OUT"; then ok "$label"
  else bad "$label (exit $got, want $want, /$rx/)"; fi
}

echo "fails_without_fix:"

new_repo good; fix_bug; write_test 'self.assertEqual(calc.add(2, 3), 5)'; commit_all good
expect 0 '^ok: tests fail without the fix \(exit 1\)' "good test fails without the fix: ok"
expect 0 '^ok:' "ok stays exit 0 under --strict" --strict
expect 2 '^error: git merge-base' "unknown base ref: error, exit 2" --base no-such-ref
expect 2 '^error: cannot run' "missing test command: error, exit 2" --test-cmd "no-such-binary-xyz"

new_repo weak; fix_bug; write_test 'self.assertTrue(True)'; commit_all weak
expect 0 '^warning: tests still pass with the fix reverted' "assertTrue(True) test: warning"
expect 1 '^warning: tests still pass' "weak test under --strict: exit 1" --strict
grep -q 'reverted: calc.py' "$OUT" && ok "warning names the reverted file" || bad "warning names the reverted file"

new_repo noimport; fix_bug
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(2 + 3, 5)\n' > tests/test_calc.py
commit_all noimport
expect 0 '^warning: tests still pass' "test that never imports calc: warning"

new_repo notests; fix_bug; commit_all fix-only
expect 0 '^warning: no test files changed' "source change without test change: warning"
expect 1 '^warning: no test files changed' "no test changes under --strict: exit 1" --strict

new_repo onlytests; write_test 'self.assertEqual(calc.add(2, 3), -1)'; commit_all tests-only
expect 0 '^warning: no non-test files changed' "test-only change: nothing to revert"

new_repo redhead; fix_bug; write_test 'self.assertEqual(calc.add(2, 3), 6)'; commit_all red
expect 0 '^warning: tests fail on HEAD \(exit 1\)' "tests already red on HEAD: reported"
expect 1 '^warning: tests fail on HEAD' "red HEAD under --strict: exit 1" --strict

new_repo custom; fix_bug
printf 'import unittest\nimport calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(calc.add(2, 3), 5)\n' > checks_calc.py
commit_all custom
expect 0 '^warning: no test files changed' "default globs do not treat checks_calc.py as a test"
expect 0 '^ok:' "--tests picks a custom test glob" --tests 'checks_*.py' \
  --test-cmd "python3 -m unittest checks_calc"

new_repo uncommitted; write_test 'self.assertEqual(calc.add(2, 3), 5)'; fix_bug
expect 0 '^warning: no test files changed' "uncommitted fix is ignored by default"
expect 0 '^ok: tests fail without the fix' "--include-uncommitted checks the uncommitted fix" \
  --include-uncommitted


# Safety: staged, unstaged and untracked changes plus a stash entry, in the repo the
# tool runs from. Every one of them must be exactly as it was.
new_repo safety; fix_bug; write_test 'self.assertEqual(calc.add(2, 3), 5)'; commit_all good
printf 'stashed\n' > notes.txt; git add notes.txt; git stash -q
printf '# staged\n' >> calc.py; git add calc.py
printf '# unstaged\n' >> calc.py
printf 'scratch\n' > untracked.txt
snapshot() {
  git status --porcelain; echo ---; git stash list; echo ---
  git diff; echo ---; git diff --cached; echo ---; git ls-files -s; echo ---; cat calc.py
}
snapshot > "$TMP/before"
for args in "" "--include-uncommitted"; do
  # shellcheck disable=SC2086
  run $args >/dev/null
  snapshot > "$TMP/after"
  if cmp -s "$TMP/before" "$TMP/after"; then ok "working tree, index and stash unchanged ${args:-(HEAD only)}"
  else bad "working tree, index or stash changed ${args:-(HEAD only)}"; diff "$TMP/before" "$TMP/after"; fi
  n="$(git worktree list | wc -l | tr -d ' ')"
  [ "$n" = "1" ] && ok "worktree removed afterwards ${args:-(HEAD only)}" \
    || bad "worktree left behind ($n entries) ${args:-(HEAD only)}"
done
ls -d "$TMPDIR"/100x-fails-without-fix-* >/dev/null 2>&1 \
  && bad "temp dir left behind" || ok "temp dir removed"

# The worktree is removed even when setup fails after it was created.
new_repo cleanup; fix_bug; write_test 'self.assertEqual(calc.add(2, 3), 5)'; commit_all good
run --test-cmd "no-such-binary-xyz" >/dev/null
n="$(git worktree list | wc -l | tr -d ' ')"
[ "$n" = "1" ] && ok "worktree removed after a failed run" || bad "worktree left after a failed run ($n)"

# The user's post-checkout hook never runs, neither for the worktree nor the revert.
new_repo hooks; fix_bug; write_test 'self.assertEqual(calc.add(2, 3), 5)'; commit_all good
printf '#!/bin/sh\ntouch "%s"\n' "$TMP/hook-ran" > .git/hooks/post-checkout
chmod +x .git/hooks/post-checkout
expect 0 '^ok: tests fail without the fix' "repo with a post-checkout hook: still ok"
[ -e "$TMP/hook-ran" ] && bad "user's post-checkout hook ran" || ok "user's post-checkout hook never ran"

# The user's own stale worktree is left for the user to prune.
new_repo stale; fix_bug; write_test 'self.assertEqual(calc.add(2, 3), 5)'; commit_all good
git worktree add -q --detach "$TMP/stale-wt" HEAD; rm -rf "$TMP/stale-wt"
run >/dev/null
git worktree list | grep -q "$TMP/stale-wt" && ok "user's stale worktree is not pruned" \
  || bad "user's stale worktree was pruned"

# Gitignored deps: named when HEAD fails without them, linked with --link-deps, and
# the user's copy survives the cleanup.
new_repo deps; fix_bug
printf 'node_modules/\n' > .gitignore
printf 'import unittest\nimport calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        open("node_modules/dep/VERSION").close()\n        self.assertEqual(calc.add(2, 3), 5)\n' > tests/test_calc.py
commit_all deps
mkdir -p node_modules/dep; printf '1.0\n' > node_modules/dep/VERSION
expect 0 '^warning: tests fail on HEAD in a fresh worktree .*node_modules is gitignored and not present there' \
  "HEAD red only for lack of node_modules: says so"
expect 0 '^ok: tests fail without the fix' "--link-deps symlinks node_modules into the worktree" --link-deps
[ -f node_modules/dep/VERSION ] && ok "symlinked node_modules survives the cleanup" \
  || bad "the user's node_modules was deleted"
ls -d "$TMPDIR"/100x-fails-without-fix-* >/dev/null 2>&1 \
  && bad "temp dir left behind after --link-deps" || ok "temp dir removed after --link-deps"

echo
echo "fails_without_fix: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
