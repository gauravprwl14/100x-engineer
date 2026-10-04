#!/usr/bin/env bash
# Regression suite for scripts/ledger.py: indexing, traceability, gaps, sharding, search.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
L="$ROOT/scripts/ledger.py"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-52s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-52s\n' "$1"; [ -s $OUT/lg.out ] && sed 's/^/       /' $OUT/lg.out | head -5; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has() { grep -q "$1" $OUT/lg.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()  { grep -q "$1" $OUT/lg.out && bad "false positive: $1" || ok "absent: $1"; }

mk_adr() { # mk_adr <n> <date> <affects> [extra-json]
  mkdir -p "$E/decisions"
  printf '# ADR-%04d: Decision %s\n\n```json meta\n{"id":"ADR-%04d","title":"Decision %s","status":"accepted","date":"%s","affects":["%s"],"options":[{"name":"a","chosen":true,"why":"x"},{"name":"b","why_not":"y"}],"assumptions":[{"id":"A1","claim":"c","verify":"true","revisit_when":"w"}]}\n```\n' \
    "$1" "$1" "$1" "$1" "$2" "$3" > "$E/decisions/ADR-$(printf '%04d' "$1")-d$1.md"
}

# No .100x.json in this repo: records go under the default root.
E=docs/engineering
C="$TMP/consumer"; mkdir -p "$C"; cd "$C"
git init -q; git config user.email e@e; git config user.name e
echo x > f.txt; git add -A; git commit -qm init

# --- empty repo must not crash ---
python3 "$L" index >$OUT/lg.out 2>&1; rc_is 0 $? "index: empty repo is clean"
python3 "$L" gaps  >$OUT/lg.out 2>&1; rc_is 0 $? "gaps: empty repo has no findings"

# --- writes into the CONSUMER repo, not the plugin ---
[ -f "$C/$E/ledger/INDEX.md" ] && ok "index: written to the consumer repo" \
  || bad "index: not written to the consumer repo"
[ ! -f "$ROOT/ledger/INDEX_CONSUMER_LEAK.md" ] && ok "index: no leak into the plugin" || bad "leak"

# --- traceability: spec + decision on the same feature must pair up ---
mkdir -p $E/specs/billing
printf '# billing — spec\n\n| field | value |\n|---|---|\n| status | ready |\n' > $E/specs/billing/spec.md
mk_adr 1 "2026-01-10" "src/billing/**"
python3 "$L" map >$OUT/lg.out 2>&1; rc_is 0 $? "map: regenerates"
grep -q "ADR-0001" "$C/$E/ledger/MAP.md" && ok "map: pairs the decision with its feature" \
  || bad "map: decision not paired"
python3 "$L" gaps >$OUT/lg.out 2>&1
no "spec with no decision"

# --- gaps: a spec with no decision is reported ---
mkdir -p $E/specs/orphan
printf '# orphan — spec\n\n| field | value |\n|---|---|\n| status | draft |\n' > $E/specs/orphan/spec.md
python3 "$L" gaps >$OUT/lg.out 2>&1; rc_is 1 $? "gaps: exits non-zero on a finding"
has "spec with no decision"

# --- gaps: a PRD with no spec is reported ---
mkdir -p $E/prds/dreaming
printf '# dreaming — PRD\n\n| field | value |\n|---|---|\n| status | draft |\n' > $E/prds/dreaming/prd.md
python3 "$L" gaps >$OUT/lg.out 2>&1
has "PRD with no spec"

# --- gaps: a decision with no affects and no feature link is unreachable ---
mkdir -p "$E/decisions"
printf '# ADR-0099: Floating\n\n```json meta\n{"id":"ADR-0099","title":"Floating","status":"accepted","date":"2026-02-01","options":[{"name":"a","chosen":true,"why":"x"},{"name":"b","why_not":"y"}],"assumptions":[{"id":"A1","claim":"c","verify":"true","revisit_when":"w"}]}\n```\n' > $E/decisions/ADR-0099-floating.md
python3 "$L" gaps >$OUT/lg.out 2>&1
has "unreachable from the code"
rm -f $E/decisions/ADR-0099-floating.md
rm -rf $E/specs/orphan $E/prds/dreaming

# --- malformed meta is an ERROR, not a crash ---
printf '# ADR-0098: Bad\n\n```json meta\n{not json}\n```\n' > $E/decisions/ADR-0098-bad.md
python3 "$L" gaps >$OUT/lg.out 2>&1
has "invalid JSON"
rm -f $E/decisions/ADR-0098-bad.md

# --- search ---
python3 "$L" find "Decision 1" >$OUT/lg.out 2>&1; rc_is 0 $? "find: runs"
has "ADR-0001"
python3 "$L" find "nothing-matches-this-xyz" >$OUT/lg.out 2>&1
has "no record mentions"

# --- sharding: below threshold is a no-op, above it splits by quarter ---
python3 "$L" shard >$OUT/lg.out 2>&1
has "nothing to shard"
for i in $(seq 2 45); do mk_adr "$i" "2026-0$(( (i % 3) + 1 ))-15" "src/a$((i%4))/**"; done
git add -A >/dev/null 2>&1; git commit -qm bulk >/dev/null 2>&1
python3 "$L" gaps >$OUT/lg.out 2>&1
has "run \`ledger.py shard\`"
# shard MOVES FILES, so it must do nothing without --yes
python3 "$L" shard >$OUT/lg.out 2>&1; rc_is 0 $? "shard: prints a plan at volume"
has "would move 45 record"
has "Nothing has changed"
[ ! -d "$C/$E/decisions/2026" ] && ok "shard: moved nothing without --yes" \
  || bad "shard: moved files without consent"
python3 "$L" shard --yes >$OUT/lg.out 2>&1; rc_is 0 $? "shard: --yes performs the move"
has "moved 45 record"
[ -d "$C/$E/decisions/2026" ] && ok "shard: created year/quarter dirs" || bad "shard: no shards"
SHARDED=$(find "$C/$E/decisions" -name 'ADR-*.md' | wc -l | tr -d ' ')
[ "$SHARDED" -eq 45 ] && ok "shard: all 45 records preserved" || bad "shard: lost records ($SHARDED)"
[ -f "$C/$E/decisions/2026/Q1/INDEX.md" ] && ok "shard: per-shard index written" || bad "shard: no shard index"

# --- records remain discoverable and searchable after sharding ---
python3 "$L" index >$OUT/lg.out 2>&1
# 45 sharded ADRs + the billing spec
has "46 records"
# links are relative to the generated page, so every one must resolve from there
python3 "$L" map >/dev/null 2>&1
python3 - "$C/$E/ledger/INDEX.md" "$C/$E/ledger/MAP.md" >$OUT/lg.out 2>&1 <<'PY'
import pathlib, re, sys
dead = [f"{p}: {h}" for p in map(pathlib.Path, sys.argv[1:])
        for h in re.findall(r"\]\(([^)#]+\.md)\)", p.read_text())
        if not (p.parent / h).resolve().is_file()]
print("\n".join(dead) or "all links resolve"); sys.exit(1 if dead else 0)
PY
rc_is 0 $? "index/map: every record link resolves from the page"
grep -q "](../specs/billing/spec.md)" "$C/$E/ledger/INDEX.md" && ok "index: page-relative link to the spec" \
  || bad "index: spec link not page-relative"
top=0; for d in ledger decisions specs prds; do [ -e "$C/$d" ] && top=1; done
[ "$top" -eq 0 ] && ok "nothing written at the repo top level" || bad "wrote a record dir at the repo top level"
python3 "$L" find "ADR-0033" >$OUT/lg.out 2>&1
has "2026/Q"
python3 "$L" shard --yes >$OUT/lg.out 2>&1
has "nothing to shard"

cd "$ROOT"
echo
echo "ledger: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
