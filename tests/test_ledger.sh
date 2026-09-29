#!/usr/bin/env bash
# Regression suite for scripts/ledger.py: indexing, traceability, gaps, sharding, search.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
L="$ROOT/scripts/ledger.py"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-52s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-52s\n' "$1"; [ -s /tmp/lg.out ] && sed 's/^/       /' /tmp/lg.out | head -5; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has() { grep -q "$1" /tmp/lg.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()  { grep -q "$1" /tmp/lg.out && bad "false positive: $1" || ok "absent: $1"; }

mk_adr() { # mk_adr <n> <date> <affects> [extra-json]
  mkdir -p decisions
  printf '# ADR-%04d: Decision %s\n\n```json meta\n{"id":"ADR-%04d","title":"Decision %s","status":"accepted","date":"%s","affects":["%s"],"options":[{"name":"a","chosen":true,"why":"x"},{"name":"b","why_not":"y"}],"assumptions":[{"id":"A1","claim":"c","verify":"true","revisit_when":"w"}]}\n```\n' \
    "$1" "$1" "$1" "$1" "$2" "$3" > "decisions/ADR-$(printf '%04d' "$1")-d$1.md"
}

C="$TMP/consumer"; mkdir -p "$C"; cd "$C"
git init -q; git config user.email e@e; git config user.name e
echo x > f.txt; git add -A; git commit -qm init

# --- empty repo must not crash ---
python3 "$L" index >/tmp/lg.out 2>&1; rc_is 0 $? "index: empty repo is clean"
python3 "$L" gaps  >/tmp/lg.out 2>&1; rc_is 0 $? "gaps: empty repo has no findings"

# --- writes into the CONSUMER repo, not the plugin ---
[ -f "$C/ledger/INDEX.md" ] && ok "index: written to the consumer repo" \
  || bad "index: not written to the consumer repo"
[ ! -f "$ROOT/ledger/INDEX_CONSUMER_LEAK.md" ] && ok "index: no leak into the plugin" || bad "leak"

# --- traceability: spec + decision on the same feature must pair up ---
mkdir -p specs/billing
printf '# billing — spec\n\n| field | value |\n|---|---|\n| status | ready |\n' > specs/billing/spec.md
mk_adr 1 "2026-01-10" "src/billing/**"
python3 "$L" map >/tmp/lg.out 2>&1; rc_is 0 $? "map: regenerates"
grep -q "ADR-0001" "$C/ledger/MAP.md" && ok "map: pairs the decision with its feature" \
  || bad "map: decision not paired"
python3 "$L" gaps >/tmp/lg.out 2>&1
no "spec with no decision"

# --- gaps: a spec with no decision is reported ---
mkdir -p specs/orphan
printf '# orphan — spec\n\n| field | value |\n|---|---|\n| status | draft |\n' > specs/orphan/spec.md
python3 "$L" gaps >/tmp/lg.out 2>&1; rc_is 1 $? "gaps: exits non-zero on a finding"
has "spec with no decision"

# --- gaps: a PRD with no spec is reported ---
mkdir -p prds/dreaming
printf '# dreaming — PRD\n\n| field | value |\n|---|---|\n| status | draft |\n' > prds/dreaming/prd.md
python3 "$L" gaps >/tmp/lg.out 2>&1
has "PRD with no spec"

# --- gaps: a decision with no affects and no feature link is unreachable ---
mkdir -p decisions
printf '# ADR-0099: Floating\n\n```json meta\n{"id":"ADR-0099","title":"Floating","status":"accepted","date":"2026-02-01","options":[{"name":"a","chosen":true,"why":"x"},{"name":"b","why_not":"y"}],"assumptions":[{"id":"A1","claim":"c","verify":"true","revisit_when":"w"}]}\n```\n' > decisions/ADR-0099-floating.md
python3 "$L" gaps >/tmp/lg.out 2>&1
has "unreachable from the code"
rm -f decisions/ADR-0099-floating.md
rm -rf specs/orphan prds/dreaming

# --- malformed meta is an ERROR, not a crash ---
printf '# ADR-0098: Bad\n\n```json meta\n{not json}\n```\n' > decisions/ADR-0098-bad.md
python3 "$L" gaps >/tmp/lg.out 2>&1
has "invalid JSON"
rm -f decisions/ADR-0098-bad.md

# --- search ---
python3 "$L" find "Decision 1" >/tmp/lg.out 2>&1; rc_is 0 $? "find: runs"
has "ADR-0001"
python3 "$L" find "nothing-matches-this-xyz" >/tmp/lg.out 2>&1
has "no record mentions"

# --- sharding: below threshold is a no-op, above it splits by quarter ---
python3 "$L" shard >/tmp/lg.out 2>&1
has "nothing to shard"
for i in $(seq 2 45); do mk_adr "$i" "2026-0$(( (i % 3) + 1 ))-15" "src/a$((i%4))/**"; done
git add -A >/dev/null 2>&1; git commit -qm bulk >/dev/null 2>&1
python3 "$L" gaps >/tmp/lg.out 2>&1
has "run \`ledger.py shard\`"
python3 "$L" shard >/tmp/lg.out 2>&1; rc_is 0 $? "shard: runs at volume"
has "moved 45 record"
[ -d "$C/decisions/2026" ] && ok "shard: created year/quarter dirs" || bad "shard: no shards"
SHARDED=$(find "$C/decisions" -name 'ADR-*.md' | wc -l | tr -d ' ')
[ "$SHARDED" -eq 45 ] && ok "shard: all 45 records preserved" || bad "shard: lost records ($SHARDED)"
[ -f "$C/decisions/2026/Q1/INDEX.md" ] && ok "shard: per-shard index written" || bad "shard: no shard index"

# --- records remain discoverable and searchable after sharding ---
python3 "$L" index >/tmp/lg.out 2>&1
# 45 sharded ADRs + the billing spec
has "46 records"
python3 "$L" find "ADR-0033" >/tmp/lg.out 2>&1
has "2026/Q"
python3 "$L" shard >/tmp/lg.out 2>&1
has "nothing to shard"

cd "$ROOT"
echo
echo "ledger: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
