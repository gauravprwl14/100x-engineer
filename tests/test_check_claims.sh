#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
C="$ROOT/scripts/check_claims.py"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-50s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-50s\n' "$1"; sed 's/^/       /' /tmp/cc.out | head -5; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has() { grep -q "$1" /tmp/cc.out && ok "reports: $1" || bad "NOT reported: $1"; }

printf '# N\n\nThe session TTL is thirty days and sessions are stored in Redis now.\n' > "$TMP/bad.md"
python3 "$C" "$TMP/bad.md" >/tmp/cc.out 2>&1; rc_is 1 $? "unlabelled claim is flagged"
has "with neither"

printf '# N\n\nSession TTL is thirty days. `Verified` — src/auth/session.store.ts:42\n' > "$TMP/good.md"
python3 "$C" "$TMP/good.md" >/tmp/cc.out 2>&1; rc_is 0 $? "labelled claim passes"

printf '# N\n\nSession TTL is thirty days, per src/auth/store.ts:42 in the repo.\n' > "$TMP/cited.md"
python3 "$C" "$TMP/cited.md" >/tmp/cc.out 2>&1; rc_is 0 $? "file:line citation counts as provenance"

# code fences and tables must not be treated as prose claims
printf '# N\n\n```bash\nthe value is set here and stored in redis always\n```\n' > "$TMP/fence.md"
python3 "$C" "$TMP/fence.md" >/tmp/cc.out 2>&1; rc_is 0 $? "fenced code is not scanned"
printf '# N\n\n| a | b |\n|---|---|\n| the value is stored in redis | yes |\n' > "$TMP/tbl.md"
python3 "$C" "$TMP/tbl.md" >/tmp/cc.out 2>&1; rc_is 0 $? "table rows are not scanned"

# SOURCE: original counts as a declared provenance
printf '# N\n\nThe threshold is forty records per directory. SOURCE: original\n' > "$TMP/orig.md"
python3 "$C" "$TMP/orig.md" >/tmp/cc.out 2>&1; rc_is 0 $? "SOURCE: original counts"

# a directory scans recursively; empty input is clean
mkdir -p "$TMP/dir"; cp "$TMP/good.md" "$TMP/dir/"
python3 "$C" "$TMP/dir" >/tmp/cc.out 2>&1; rc_is 0 $? "directory scan works"
mkdir -p "$TMP/empty"
python3 "$C" "$TMP/empty" >/tmp/cc.out 2>&1; rc_is 0 $? "empty directory is clean"
has "no markdown found"

echo
echo "check_claims: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
