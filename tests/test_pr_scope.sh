#!/usr/bin/env bash
# Regression suite for pr_scope.py: every signal is planted once, and a clean change
# of each shape must stay silent.
# Run: bash tests/test_pr_scope.sh   Exits non-zero on any failure.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PS="$ROOT/scripts/pr_scope.py"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; sed 's/^/       /' "$TMP/out"; }
# expect <exit> <label> <grep-pattern|-> <not-pattern|-> [args...]
expect() {
  local want="$1" label="$2" has="$3" hasnt="$4"; shift 4
  python3 "$PS" "$@" >"$TMP/out" 2>&1; local got=$?
  if [ "$got" -ne "$want" ]; then bad "$label (exit want=$want got=$got)"; return; fi
  if [ "$has" != - ] && ! grep -q -- "$has" "$TMP/out"; then bad "$label (missing '$has')"; return; fi
  if [ "$hasnt" != - ] && grep -q -- "$hasnt" "$TMP/out"; then bad "$label (unexpected '$hasnt')"; return; fi
  ok "$label"
}
new_repo() {
  rm -rf "$TMP/r"; mkdir -p "$TMP/r"; cd "$TMP/r"
  git init -q; git config user.email t@t; git config user.name t
  git symbolic-ref HEAD refs/heads/main
  mkdir -p app/reactions app/tagging spec; echo base > app/reactions/model.rb
  echo base > app/tagging/model.rb; echo base > README.md
  git add -A; git commit -qm init
}
commit() { mkdir -p "$(dirname "$1")"; echo "$2" >> "$1"; git add -A; git commit -qm "$1"; }

echo "--- in-scope diff"
new_repo; git checkout -qb feat/reactions
commit app/reactions/model.rb r1; commit spec/reactions_spec.rb r1
expect 0 "in-scope diff: no warning" "no scope warnings" "out-of-scope" \
  --base main --scope 'app/reactions/**,spec/**'
printf 'scope: app/reactions/**, spec/**\n' > "$TMP/body.md"
expect 0 "scope read from the PR body: no warning" "no scope warnings" "out-of-scope" \
  --base main --body-file "$TMP/body.md"

echo "--- out-of-scope file"
commit app/tagging/model.rb leak
expect 0 "out-of-scope file warned, exit 0 by default" "app/tagging/model.rb: \[out-of-scope\]" - \
  --base main --scope 'app/reactions/**,spec/**'
expect 1 "--strict exits 1 on a finding" "out-of-scope" - \
  --base main --scope 'app/reactions/**,spec/**' --strict
expect 1 "PR-body scope: out-of-scope file warned" "app/tagging/model.rb: \[out-of-scope\]" - \
  --base main --body-file "$TMP/body.md" --strict
printf 'app/reactions/\nspec/   # tests\n' > .100x-scope; git add -A; git commit -qm scope
expect 0 ".100x-scope file: out-of-scope file warned" "app/tagging/model.rb: \[out-of-scope\]" \
  "app/reactions/model.rb: \[" --base main

echo "--- sibling overlap"
new_repo; git checkout -qb feat/tagging
commit app/tagging/model.rb t1
git checkout -q main; git checkout -qb feat/reactions
commit app/reactions/model.rb r1
expect 0 "sibling touching other files: no overlap" "no scope warnings" "sibling-overlap" --base main
commit app/tagging/model.rb t1-copied
expect 1 "file also changed on a sibling branch is flagged" \
  "app/tagging/model.rb: \[sibling-overlap\].*feat/tagging" "app/reactions/model.rb: \[" \
  --base main --strict
git checkout -q feat/tagging; git checkout -qb feat/reactions2
commit app/reactions/model.rb r2
expect 0 "stacked on a sibling: suggests the right --base" "use --base feat/tagging" - --base main
expect 0 "stacked, with the right --base: no warning" "no scope warnings" "sibling-overlap" \
  --base feat/tagging
git checkout -q feat/tagging
expect 0 "a branch stacked on this one is not a sibling" "feat/reactions\`" "feat/reactions2" \
  --base main

echo "--- no scope declared"
new_repo; git checkout -qb fix/one
commit app/reactions/model.rb fix; commit spec/reactions_spec.rb fix; commit README.md fix
expect 0 "clean single-area change: areas listed, no warning" "spec/: 1" "wide-diff" --base main
for d in api web worker infra; do commit "$d/x.txt" y; done
expect 1 "diff across more than 3 unrelated areas warned" "\[wide-diff\].*api, app, infra, web, worker" - \
  --base main --strict

echo "--- base resolution"
new_repo; git checkout -qb feat/x; commit app/reactions/model.rb z
expect 0 "default base falls back to main" "vs merge-base with main" -
git branch -q -m main trunk
expect 2 "no resolvable base: says so and exits 2" "no base ref" -

echo
echo "pr-scope: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
