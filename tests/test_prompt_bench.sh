#!/usr/bin/env bash
# prompt_bench.py: init scaffolds runs + plan, record/snapshot, blind is seeded and never
# leaks arms, probes run on blinded code, judge-plan scopes ground truth per task, aggregate
# reproduces round-2 numbers and catches useless/harmful/ceiling/small-n, report writes files.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIX="$ROOT/evals/fixtures/prompt-bench"
PB="$ROOT/scripts/prompt_bench.py"
TMP="$(cd "$(mktemp -d)" && pwd -P)"; OUT="$(mktemp -d)"
trap 'rm -rf "$TMP" "$OUT"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-64s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "$1"; sed 's/^/       /' "$OUT/r.out" | head -12; }
run() {
  local exp="$1" label="$2"; shift 2
  python3 "$PB" "$@" >"$OUT/r.out" 2>&1; local got=$?
  [ "$got" -eq "$exp" ] && ok "$label" || bad "$label (exit exp=$exp got=$got)"
}
has()   { grep -qF -- "$1" "$OUT/r.out" && ok "  reports $1" || bad "  NOT reported: $1"; }
hasnt() { grep -qF -- "$1" "$OUT/r.out" && bad "  unexpectedly reports $1" || ok "  does not report $1"; }
py()    { python3 -c "$1" "${@:2}" >"$OUT/r.out" 2>&1; }

export GIT_CONFIG_GLOBAL="$TMP/gitconfig" GIT_CONFIG_NOSYSTEM=1

echo "== init"
S="$TMP/spec"; mkdir -p "$S/fx-code" "$S/fx-text"
printf 'def add(a, b):\n    return a - b\n' > "$S/fx-code/calc.py"
printf 'Release notes draft.\n' > "$S/fx-text/NOTES.md"
cat > "$S/spec.json" <<'JSON'
{"category": "follow-up", "design": "paired-followup", "reps": 1,
 "arms": {"placebo": "Please double-check your answer.", "zealot": "Audit everything three times over."},
 "tasks": [
  {"id": "fix-add", "fixture_dir": "fx-code", "task_prompt": "Fix add() in calc.py.",
   "ground_truth": "SECRET-ADD: add must return a + b.",
   "probes": ["from calc import add; assert add(2, 3) == 5"]},
  {"id": "notes", "fixture_dir": "fx-text", "task_prompt": "Summarise NOTES.md.",
   "ground_truth": "SECRET-NOTES: it is a draft."}]}
JSON
B="$TMP/bench"
run 0 "init from a tiny spec" init "$B" --spec "$S/spec.json"
has "2 task(s) x 2 arm(s) x 1 rep(s) = 4 runs"
for f in plan.json ARMS.md GROUND_TRUTH.md fixtures/fix-add/calc.py runs/fix-add-1/calc.py runs/fix-add-2/calc.py runs/notes-2/NOTES.md; do
  [ -f "$B/$f" ] && ok "  created $f" || bad "  missing $f"
done
[ -d "$B/runs/fix-add-1/.git" ] && git -C "$B/runs/fix-add-1" log --oneline | grep -q fixture \
  && ok "  each run is a fresh git repo with the fixture committed" || bad "  run is not a git repo"
[ ! -e "$B/runs/GROUND_TRUTH.md" ] && ! grep -rq SECRET "$B/runs" && ok "  ground truth kept out of runs/" || bad "  ground truth reachable in runs/"
py 'import json,sys
p=json.load(open(sys.argv[1])); r={x["id"]:x for x in p["runs"]}
assert [x["arm"] for x in p["runs"] if x["task"]=="fix-add"]==["placebo","zealot"], p["runs"]
a=r["fix-add-1"]; assert "Fix add() in calc.py." in a["prompt_v1"] and "/runs/fix-add-1" in a["prompt_v1"]
assert "do not use the network" in a["prompt_v1"] and "answer_v1.md" in a["prompt_v1"]
assert a["prompt_v2"].startswith("Please double-check your answer.") and "answer_v2.md" in a["prompt_v2"]
assert r["fix-add-2"]["prompt_v2"].startswith("Audit everything") and "SECRET" not in json.dumps(p)
assert p["tasks"][0]["code"] is True and p["tasks"][1]["code"] is False' "$B/plan.json" \
  && ok "  plan.json: arm per run, isolated runner prompt, follow-up text, no ground truth" || bad "  plan.json content"
run 1 "init into a non-empty dir is refused" init "$B" --spec "$S/spec.json"
python3 - "$S/spec.json" "$S/noplacebo.json" <<'PY'
import json, sys; s = json.load(open(sys.argv[1])); s["arms"].pop("placebo"); json.dump(s, open(sys.argv[2], "w"))
PY
run 1 "a spec without a placebo arm is refused" init "$TMP/b2" --spec "$S/noplacebo.json"
has "placebo"

echo "== record + snapshot"
run 0 "record v1" record "$B" --run fix-add-1 --phase v1 --tokens 41000 --ms 30000
run 1 "record the same run+phase twice is refused" record "$B" --run fix-add-1 --phase v1 --tokens 1 --ms 1
run 1 "record an unknown run is refused" record "$B" --run nope-9 --phase v1 --tokens 1 --ms 1
head -1 "$B/metrics.csv" | grep -qx "run,arm,phase,tokens,duration_ms" && grep -q "^fix-add-1,placebo,v1,41000,30000" "$B/metrics.csv" \
  && ok "  metrics.csv row carries the arm" || bad "  metrics.csv content"
run 1 "snapshot before answer_v1.md is refused" snapshot "$B" --run fix-add-1
for n in 1 2; do
  d="$B/runs/fix-add-$n"
  printf 'def add(a, b):\n    return a + b\n' > "$d/calc.py"
  printf 'Fixed it in %s/calc.py.\n' "$d" > "$d/answer_v1.md"
  python3 "$PB" snapshot "$B" --run "fix-add-$n" >/dev/null 2>&1 || bad "snapshot fix-add-$n"
done
[ -f "$B/snapshots/fix-add-1/v1/calc.py" ] && [ ! -e "$B/snapshots/fix-add-1/v1/answer_v1.md" ] \
  && ok "snapshot saves v1 code, not the answer" || bad "snapshot content"
run 1 "snapshot of a non-code task is refused" snapshot "$B" --run notes-1
printf 'def add(a, b):\n    return a * b\n' > "$B/runs/fix-add-2/calc.py"
for n in 1 2; do
  printf 'Re-checked: still fine.\n' > "$B/runs/fix-add-$n/answer_v2.md"
  printf 'A draft.\n' > "$B/runs/notes-$n/answer_v1.md"
done
run 1 "blind with a missing answer is refused" blind "$B" --seed 7
has "notes-1/answer_v2.md"
for n in 1 2; do printf 'It is a draft of release notes.\n' > "$B/runs/notes-$n/answer_v2.md"; done

echo "== blind"
run 0 "blind --seed 7" blind "$B" --seed 7
has "8 blind answers"
cp "$B/blind_key.json" "$TMP/key7"; find "$B/blind" -type f | sort > "$TMP/files7"
run 1 "re-blind without --force is refused" blind "$B" --seed 7
run 0 "blind --force, same seed" blind "$B" --seed 7 --force
cmp -s "$B/blind_key.json" "$TMP/key7" && ok "  same seed -> identical key" || bad "  same seed gave a different key"
run 0 "blind --force, other seed" blind "$B" --seed 8 --force
cmp -s "$B/blind_key.json" "$TMP/key7" && bad "  other seed gave the same key" || ok "  other seed -> different shuffle"
run 0 "blind --seed 7 again" blind "$B" --seed 7 --force
grep -rqiE "placebo|zealot|Audit everything|double-check" "$B/blind" && bad "  arm name or prompt leaked into blind/" || ok "  no arm name or prompt in blind/"
grep -rq "/runs/fix-add\|answer_v" "$B/blind" && bad "  run path leaked into blind/" || ok "  run paths scrubbed to <workdir>"
[ ! -e "$B/runs/blind_key.json" ] && [ -f "$B/blind_key.json" ] && ok "  key kept outside runs/ and blind/" || bad "  key location"
py 'import json,sys
k=json.load(open(sys.argv[1]))["labels"]
assert len(k)==8 and all(set(v)>={"task","run","arm","rep","version","chars"} for v in k.values())
assert sorted(l for l in k if k[l]["task"]=="fix-add")==["T1-01","T1-02","T1-03","T1-04"]' "$B/blind_key.json" \
  && ok "  key maps each label to run, arm, version" || bad "  key content"
V1=$(python3 -c 'import json,sys; k=json.load(open(sys.argv[1]))["labels"]; print(next(l for l,v in k.items() if v["run"]=="fix-add-2" and v["version"]=="v1"))' "$B/blind_key.json")
V2=$(python3 -c 'import json,sys; k=json.load(open(sys.argv[1]))["labels"]; print(next(l for l,v in k.items() if v["run"]=="fix-add-2" and v["version"]=="v2"))' "$B/blind_key.json")
grep -q "a + b" "$B/blind/fix-add/$V1.md" && grep -q "a \* b" "$B/blind/fix-add/$V2.md" \
  && ok "  v1 label shows the snapshot code, v2 the final code" || bad "  code versions mixed up"
ls -A "$B/blind/fix-add/$V2.files" > "$OUT/r.out"; [ "$(cat "$OUT/r.out")" = "calc.py" ] && ok "  probe tree holds code only (no answers, no .git)" || bad "  probe tree has extra files"

echo "== probe"
run 0 "probe passes on the correct v1 fix" probe "$B" --label "$V1"
has "1/1 probes pass"
run 1 "probe fails on the broken v2 code" probe "$B" --label "$V2"
has "FAIL probe 1"
run 1 "probe on a non-code label is refused" probe "$B" --label T2-01

echo "== judge-plan"
run 0 "judge-plan" judge-plan "$B"
has "=== judge prompt: fix-add"; has "=== judge prompt: notes"; has "SECRET-ADD"; has "probe $B --label <LABEL>"
has "process leakage"; has "scores/fix-add.json"; has "Do not open"
hasnt "zealot"
run 0 "judge-plan --task notes" judge-plan "$B" --task notes
hasnt "SECRET-ADD"; has "SECRET-NOTES"
run 1 "aggregate before any score is refused" aggregate "$B"

echo "== aggregate: round 2 (real numbers)"
run 0 "aggregate round2" aggregate "$FIX/round2"
has "| placebo | reference (placebo) | +1.5 |"
has "| user | no better than placebo (within noise) | +2.42 | +0.92 | 0.375 | 4/1/1 |"
has "| A | no better than placebo (within noise) | +1.5 | +0.0 | 1.0 | 3/1/2 |"
has "| B | no better than placebo (within noise) | +1.92 | +0.42 | 0.2188 | 5/0/1 |"
has "| h3-fix | placebo | 4.5 | 7.5 | +3 |"
has "length: arm A answers are +32.4% longer"
hasnt "ceiling"; hasnt "scored runs for arm"
run 0 "aggregate --json" aggregate "$FIX/round2" --json
cp "$OUT/r.out" "$TMP/agg.json"
py 'import json,sys
d=json.load(open(sys.argv[1])); a=d["arms"]
assert a["user"]["all"]["delta"]==2.42 and a["placebo"]["all"]["delta"]==1.5, a["user"]["all"]
assert round(a["placebo"]["all"]["ms_v2"]/1000,1)==91.0 and a["user"]["all"]["improved"]==6' "$TMP/agg.json" \
  && ok "  json: deltas and follow-up duration" || bad "  json content"

echo "== aggregate: synthetic useless / harmful / strong / ceiling"
run 0 "aggregate synthetic" aggregate "$FIX/synthetic"
has "| useless | no better than placebo (within noise) | +0.5 | +0.0 | 1.0 | 0/6/0 |"
has "| harmful | worse | -1 | -1.5 | 0.0312 | 0/0/6 |"
has "| strong | better than placebo | +2.17 | +1.67 | 0.0312 | 6/0/0 |"
has "ceiling: task t3 baseline mean 9"
hasnt "ceiling: task t1"; hasnt "ceiling: task t2"
has "length: arm strong"; hasnt "length: arm useless"
SM="$TMP/small"; cp -R "$FIX/synthetic" "$SM"; mv "$SM/scores/t3.json" "$TMP/t3.off"
run 0 "aggregate with one task unscored" aggregate "$SM"
has "n=4 scored runs for arm strong"; has "scores/t3.json missing"
run 0 "aggregate parallel-arms" aggregate "$FIX/parallel"
has "| rule | better than placebo | 7.5 | +2.0 | 0.0312 | 6/0/0 |"

echo "== report"
RP="$TMP/rep"; cp -R "$FIX/synthetic" "$RP"
run 0 "report" report "$RP"
[ -f "$RP/REPORT.md" ] && [ -f "$RP/INDEX.md" ] && ok "  wrote REPORT.md and INDEX.md" || bad "  report files missing"
cp "$RP/REPORT.md" "$OUT/r.out"
has "**Result:** strong: better than placebo."; has "## Contents"; has "## Category and placement"; has "## Cost"
has "Stop-hook re-check"; has "Do not use it. Keep the placebo follow-up."; has "ceiling: task t3"
py 'import sys
t=open(sys.argv[1]).read(); assert t.index("| arm | verdict |") < t.index("## Contents") < t.index("## Verdict"), "order"' "$RP/REPORT.md" \
  && ok "  summary table comes before Contents and Verdict" || bad "  report section order"
cp "$RP/INDEX.md" "$OUT/r.out"; has "| [REPORT.md](REPORT.md) |"; has "blind_key.json"
RP2="$TMP/rep2"; cp -R "$FIX/round2" "$RP2"
run 0 "report round2" report "$RP2"
has "No tested arm beat the placebo beyond noise"
cp "$RP2/REPORT.md" "$OUT/r.out"; has "The second pass is the lever, not this wording"

echo "== safety"
run 2 "no subcommand is a usage error"
run 2 "a bench that is not a directory is a usage error" aggregate "$TMP/missing"

echo
echo "prompt_bench: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
