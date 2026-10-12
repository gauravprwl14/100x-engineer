#!/usr/bin/env bash
# coverage_check.py must compute the accuracy log's coverage numbers from the guide's
# markup: a fully tagged guide passes, and a missing, unknown or excluded-but-tagged
# key point fails with its id named.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CC="$ROOT/scripts/coverage_check.py"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; sed 's/^/       /' "$TMP/out" | head -8; }
# expect <exit code> <grep pattern> <label> -- <command...>
expect() {
  local want="$1" pat="$2" label="$3"; shift 4
  "$@" >"$TMP/out" 2>&1; local got=$?
  if [ "$got" -eq "$want" ] && grep -qE -- "$pat" "$TMP/out"; then ok "$label"
  else echo "exit $got, wanted $want; pattern: $pat" >>"$TMP/out"; bad "$label"; fi
}

cat >"$TMP/inventory.json" <<'JSON'
{"source": "test talk", "key_points": [
  {"id": "kp-1", "text": "Temperature scales randomness", "page": "temperature"},
  {"id": "kp-2", "text": "Top-p trims the tail", "page": "sampling"},
  {"id": "kp-3", "text": "Seed makes runs repeatable", "page": "sampling"},
  {"id": "kp-4", "text": "Speaker's lunch plans", "excluded": "personal tangent"}]}
JSON

mkdir -p "$TMP/good" "$TMP/missing" "$TMP/md" "$TMP/unknown" "$TMP/excl"
cat >"$TMP/good/index.html" <<'HTML'
<section id="temperature"><p data-kp="kp-1">Temperature…</p></section>
<section id="sampling"><li data-kp='kp-2 kp-3'>Top-p and seed</li></section>
HTML
# accuracy-log.md is never scanned, so a kp id written there does not count as coverage.
printf '| kp-3 | covered |\n' >"$TMP/missing/accuracy-log.md"
cat >"$TMP/missing/index.html" <<'HTML'
<!-- data-kp="kp-3" inside a comment is documentation, not coverage -->
<section id="temperature"><p data-kp="kp-1">Temperature…</p></section>
<section id="sampling"><li data-kp="kp-2">Top-p</li></section>
HTML
cat >"$TMP/md/INDEX.md" <<'MD'
# Guide
- [Sampling](sampling.md) <!-- kp:kp-1 -->
MD
cat >"$TMP/md/sampling.md" <<'MD'
[← Index](INDEX.md)
Top-p and seed. <!-- kp: kp-2, kp-3 -->
MD
cat >"$TMP/unknown/index.html" <<'HTML'
<p data-kp="kp-1 kp-2 kp-3 kp-99">all</p>
HTML
cat >"$TMP/excl/index.html" <<'HTML'
<p data-kp="kp-1 kp-2 kp-3 kp-4">all, plus the excluded tangent</p>
HTML
printf '{"key_points": [{"id": "kp-1"}, {"id": "kp-1"}]}' >"$TMP/dup.json"

expect 0 "covered: 3 · intentionally excluded: 1 · missing: 0" \
  "good: every key point tagged in HTML -> PASS with computed counts" -- python3 "$CC" "$TMP/inventory.json" "$TMP/good/index.html"
expect 1 "MISSING  kp-3" \
  "missing: an untagged key point fails and is named" -- python3 "$CC" "$TMP/inventory.json" "$TMP/missing"
expect 1 "covered: 2 .* missing: 1" \
  "missing: comment and accuracy-log mentions do not count as coverage" -- python3 "$CC" "$TMP/inventory.json" "$TMP/missing"
expect 0 "covered: 3" \
  "markdown: <!-- kp:... --> markers across a directory" -- python3 "$CC" "$TMP/inventory.json" "$TMP/md"
expect 1 "UNKNOWN  kp-99" \
  "unknown: a tag with no inventory entry fails" -- python3 "$CC" "$TMP/inventory.json" "$TMP/unknown"
expect 1 "EXCLUDED-BUT-TAGGED  kp-4" \
  "excluded: an excluded key point that is tagged fails" -- python3 "$CC" "$TMP/inventory.json" "$TMP/excl"
expect 2 "duplicate key point id 'kp-1'" \
  "bad input: duplicate inventory ids exit 2" -- python3 "$CC" "$TMP/dup.json" "$TMP/good"
expect 2 "guide path not found" \
  "bad input: missing guide path exits 2" -- python3 "$CC" "$TMP/inventory.json" "$TMP/nope"
expect 0 '"missing": \[\]' \
  "--json reports the same numbers" -- python3 "$CC" "$TMP/inventory.json" "$TMP/good" --json

echo "test_coverage_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
