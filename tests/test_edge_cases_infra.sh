#!/usr/bin/env bash
# Regression suite for scripts/data/edge_cases_infra.json -- the component-keyed
# failure-mode catalogue (cache, queue, cron, webhook, third-party-api,
# multi-tenancy, pii-compliance, batch-job, file-storage, notification) that
# ships alongside, but separate from, scripts/data/edge_cases.json.
#
# Two things must both hold: the catalogue's own shape must be valid, and
# scripts/plan_feature.py must actually be able to load and use it -- a
# catalogue that parses but that the tool can't reach is dead weight.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$ROOT/scripts/data/edge_cases_infra.json"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
OUT="$TMP/out"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-58s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "$1"; [ -s "$OUT" ] && sed 's/^/       /' "$OUT" | head -6; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -q "$1" "$OUT" && ok "reports: $1" || bad "does NOT report: $1"; }

EXPECT_KINDS="cache queue cron webhook third-party-api multi-tenancy pii-compliance batch-job file-storage notification"

# ---------- 1. file exists and is untouched-sibling of edge_cases.json ----------
[ -f "$DATA" ] && ok "edge_cases_infra.json exists" || bad "edge_cases_infra.json missing"
[ -f "$ROOT/scripts/data/edge_cases.json" ] && ok "edge_cases.json still present (not merged away)" \
  || bad "edge_cases.json missing"

# ---------- 2. shape: valid JSON, 6-10 entries of 3 non-empty strings per kind ----------
python3 - "$DATA" "$EXPECT_KINDS" > "$OUT" 2>&1 <<'PY'
import json, sys
path, expect = sys.argv[1], sys.argv[2].split()
d = json.load(open(path))
kinds = [k for k in d if not k.startswith("_")]
missing = [k for k in expect if k not in kinds]
extra = [k for k in kinds if k not in expect]
if missing:
    print(f"MISSING kinds: {missing}"); sys.exit(1)
if extra:
    print(f"UNEXPECTED extra kinds: {extra}"); sys.exit(1)
bad = []
for k in kinds:
    v = d[k]
    if not isinstance(v, list) or not (6 <= len(v) <= 10):
        bad.append(f"{k}: {len(v) if isinstance(v, list) else type(v)} entries (want 6-10)")
        continue
    for e in v:
        if not (isinstance(e, list) and len(e) == 3 and all(isinstance(x, str) and x.strip() for x in e)):
            bad.append(f"{k}: malformed entry {e!r}")
if bad:
    print("SHAPE ERRORS:\n" + "\n".join(bad)); sys.exit(1)
print(f"shape OK: {len(kinds)} kinds, " + ", ".join(f"{k}={len(d[k])}" for k in sorted(kinds)))
PY
rc_is 0 $? "infra catalogue: valid shape (10 kinds, 6-10 entries of 3 strings each)"
has "shape OK"

# ---------- 3. no kind name collides with edge_cases.json (additive, not overlapping) ----------
python3 - > "$OUT" 2>&1 <<PY
import json
core = json.load(open("$ROOT/scripts/data/edge_cases.json"))
infra = json.load(open("$DATA"))
core_k = {k for k in core if not k.startswith("_")}
infra_k = {k for k in infra if not k.startswith("_")}
overlap = core_k & infra_k
if overlap:
    print(f"COLLISION: kinds defined in both files: {sorted(overlap)}")
    raise SystemExit(1)
print("no kind-name collision")
PY
rc_is 0 $? "infra catalogue: no kind collides with edge_cases.json"

# ---------- 4. no verbatim duplicate 'what' text vs edge_cases.json's realtime/integration/payment ----------
# (the task brief: reference those kinds' scenarios, don't restate them)
python3 - > "$OUT" 2>&1 <<PY
import json
core = json.load(open("$ROOT/scripts/data/edge_cases.json"))
infra = json.load(open("$DATA"))
referenced = set()
for k in ("realtime", "integration", "payment"):
    for e in core.get(k, []):
        referenced.add(e[0])
dupes = []
for k, entries in infra.items():
    if k.startswith("_"):
        continue
    for e in entries:
        if e[0] in referenced:
            dupes.append((k, e[0]))
if dupes:
    print(f"DUPLICATED from realtime/integration/payment: {dupes}")
    raise SystemExit(1)
print("no verbatim duplication of realtime/integration/payment entries")
PY
rc_is 0 $? "infra catalogue: does not duplicate realtime/integration/payment verbatim"

# ---------- 5. plan_feature.py loads the merged catalogue: KINDS includes the new ones ----------
python3 - > "$OUT" 2>&1 <<PY
import sys
sys.path.insert(0, "$ROOT/scripts")
import plan_feature as pf
want = set("$EXPECT_KINDS".split())
have = set(pf.KINDS)
missing = want - have
if missing:
    print(f"plan_feature.py KINDS missing: {sorted(missing)}")
    raise SystemExit(1)
# original kinds must still be present -- this is a merge, not a replacement
orig = {"universal", "auth", "crud", "payment", "upload", "search", "realtime", "migration", "integration"}
gone = orig - have
if gone:
    print(f"plan_feature.py lost original kinds: {sorted(gone)}")
    raise SystemExit(1)
print(f"plan_feature.py KINDS: {len(have)} total, all {len(want)} infra kinds present, all 9 original kinds present")
PY
rc_is 0 $? "plan_feature.py: merged KINDS includes infra + original kinds"
has "all 9 original kinds present"

# ---------- 6. `plan_feature.py new --kind <infra-kind>` works for every new kind, in a consumer repo ----------
CONS="$TMP/consumer"; mkdir -p "$CONS"; cd "$CONS"
git init -q; git config user.email e@e; git config user.name e
echo x > f.txt; git add -A; git commit -qm init

FAILED_KINDS=""
for k in $EXPECT_KINDS; do
  name="feat-$(echo "$k" | tr -cd 'a-z0-9')"
  python3 "$ROOT/scripts/plan_feature.py" new "$name" --kind "$k" > "$OUT" 2>&1
  rc=$?
  if [ "$rc" -ne 0 ] || [ ! -f "$CONS/specs/$name/spec.md" ]; then
    FAILED_KINDS="$FAILED_KINDS $k"
  fi
done
if [ -z "$FAILED_KINDS" ]; then
  ok "plan_feature.py new: all 10 infra kinds scaffold a spec individually"
else
  bad "plan_feature.py new: failed for kinds:$FAILED_KINDS"
fi

# ---------- 7. combining an infra kind with an existing kind works and dedups edge cases ----------
python3 "$ROOT/scripts/plan_feature.py" new checkout --kind payment,webhook,queue > "$OUT" 2>&1
rc_is 0 $? "plan_feature.py new: combines payment (core) + webhook,queue (infra)"
has "checkout"
grep -q "edge cases seeded" "$OUT" && ok "reports edge case count for combined kinds" \
  || bad "no edge case count reported"

# ---------- 8. unknown kind still rejected (regression: merge must not loosen validation) ----------
python3 "$ROOT/scripts/plan_feature.py" new bogus --kind notarealkind > "$OUT" 2>&1
rc_is 2 $? "plan_feature.py new: unknown kind still rejected after merge"

# ---------- 9. audit runs against a spec scaffolded from an infra-only kind ----------
python3 "$ROOT/scripts/plan_feature.py" audit "$CONS/specs/feat-cache" > "$OUT" 2>&1
rc_is 1 $? "plan_feature.py audit: fresh infra-kind spec correctly fails (TODO cases)"
has "still TODO"

cd "$ROOT"

echo
echo "edge-cases-infra: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
