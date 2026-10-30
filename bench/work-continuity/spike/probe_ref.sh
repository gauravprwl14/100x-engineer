#!/usr/bin/env bash
# Phase 0 probe: does the remote accept refs/100x/*, is it hidden from a normal clone, and is a
# claim pushed with --force-with-lease a real compare-and-swap? Pushes only refs/100x/probe-*
# and deletes them before exiting. Usage: probe_ref.sh [remote]   (default: origin)
set -euo pipefail
REMOTE="${1:-origin}"
RUN="probe-$(date +%s)"
EVENTS="refs/100x/$RUN/work"
CLAIM="refs/100x/$RUN/claims/pr-1"
URL="$(git remote get-url "$REMOTE")"
pass=0; fail=0
check() { if "$@"; then echo "PASS  $NAME"; pass=$((pass+1)); else echo "FAIL  $NAME"; fail=$((fail+1)); fi; }
cleanup() { git push -q "$REMOTE" ":$EVENTS" ":$CLAIM" 2>/dev/null || true; git update-ref -d "$EVENTS" 2>/dev/null || true; }
trap cleanup EXIT

commit_with() {  # commit_with <file name> <content> [parent] -> prints the new commit sha
  local blob tree
  blob=$(printf '%s\n' "$2" | git hash-object -w --stdin)
  tree=$(printf '100644 blob %s\t%s\n' "$blob" "$1" | git mktree)
  if [ -n "${3:-}" ]; then git commit-tree "$tree" -p "$3" -m "$1"; else git commit-tree "$tree" -m "$1"; fi
}

NAME="remote accepts a push to $EVENTS"
c1=$(commit_with "e1.json" '{"schema":1,"type":"note","text":"probe"}')
check git push -q "$REMOTE" "$c1:$EVENTS"

NAME="ref is listed by ls-remote"
check bash -c "git ls-remote '$REMOTE' '$EVENTS' | grep -q '$c1'"

NAME="a default clone does not fetch refs/100x/*"
tmp=$(mktemp -d)
git clone -q --no-checkout --filter=blob:none "$URL" "$tmp/c" 2>/dev/null
check bash -c "! git -C '$tmp/c' for-each-ref refs/100x | grep -q ."

NAME="an explicit refspec fetches it"
check bash -c "git -C '$tmp/c' fetch -q origin '+refs/100x/$RUN/*:refs/100x/$RUN/*' && git -C '$tmp/c' rev-parse -q --verify '$EVENTS' >/dev/null"

NAME="append race: a stale non-fast-forward push is rejected"
c2=$(commit_with "e2.json" '{"schema":1,"type":"note","text":"writer A"}' "$c1")
c3=$(commit_with "e3.json" '{"schema":1,"type":"note","text":"writer B"}' "$c1")
git push -q "$REMOTE" "$c2:$EVENTS"
check bash -c "! git push -q '$REMOTE' '$c3:$EVENTS' 2>/dev/null"

NAME="claim CAS: the first claimant of a free PR wins"
a=$(commit_with "claim.json" '{"holder":"session-A"}')
b=$(commit_with "claim.json" '{"holder":"session-B"}')
check git push -q --force-with-lease="$CLAIM:" "$REMOTE" "$a:$CLAIM"

NAME="claim CAS: a second claimant expecting a free PR is refused"
check bash -c "! git push -q --force-with-lease='$CLAIM:' '$REMOTE' '$b:$CLAIM' 2>/dev/null"

NAME="claim CAS: a takeover naming the current holder's sha succeeds"
check git push -q --force-with-lease="$CLAIM:$a" "$REMOTE" "$b:$CLAIM"

rm -rf "$tmp"
echo "probe_ref: $pass passed, $fail failed (remote $REMOTE, refs removed on exit)"
[ "$fail" -eq 0 ]
