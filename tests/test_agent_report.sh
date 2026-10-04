#!/usr/bin/env bash
# Regression suite for scripts/agent_report.py: every row of the OPERATING-MODEL §3
# rejection table is detected, valid reports pass, extract takes the LAST json block,
# replay catches a false exit-code claim and runs nothing without --yes.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EX="$ROOT/examples/orchestration"
M="$EX/messages"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
A="$ROOT/scripts/agent_report.py"
O="$TMP/ar.out"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; [ -s "$O" ] && sed 's/^/       /' "$O" | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" "$O" && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -qF -- "$1" "$O" && bad "false positive: $1" || ok "absent: $1"; }

# --- extract: the LAST fenced json block, not the earlier draft ---
python3 "$A" extract "$M/done-valid.md" -o "$TMP/r.json" >"$O" 2>&1; rc_is 0 $? "extract: writes the report"
python3 -c "import json,sys; d=json.load(open('$TMP/r.json')); sys.exit(0 if d['status']=='done' and 'evidence' in d else 1)" \
  && ok "extract: picked the LAST json block (status done, not the needs-decision draft)" \
  || bad "extract: picked an earlier block"
python3 "$A" extract - < "$M/needs-decision.md" >"$O" 2>&1; rc_is 0 $? "extract: reads stdin"
has '"status": "needs-decision"'
printf 'no report here\n```python\nx = 1\n```\n' > "$TMP/none.md"
python3 "$A" extract "$TMP/none.md" >"$O" 2>&1; rc_is 2 $? "extract: no json block is exit 2"
has "no fenced"

# --- lint: valid reports pass, as message or as bare JSON ---
for f in done-valid needs-decision needs-decision-frontend; do
  python3 "$A" lint "$M/$f.md" --graph "$EX/plan.json" >"$O" 2>&1; rc_is 0 $? "lint: $f passes"
done
python3 "$A" lint "$TMP/r.json" >"$O" 2>&1; rc_is 0 $? "lint: accepts an extracted bare JSON report"

# --- lint: each §3 rejection row ---
lint_fails() { # lint_fails <message> <expected substring> [extra args]
  local f="$1" msg="$2"; shift 2
  python3 "$A" lint "$M/$f.md" "$@" >"$O" 2>&1
  rc_is 1 $? "lint: $f exits 1"; has "$msg"
}
lint_fails done-no-evidence          "status done with no evidence"
lint_fails done-nonzero-evidence     "evidence 'test -f missing-file.txt' exited 1"
lint_fails one-way-decision          "decision D2 is a one-way door"
lint_fails needs-decision-unblocked  "needs-decision with no blocking question or plan issue"
lint_fails done-with-blocking        "status done while blocking item(s) P1"
lint_fails class-c-assumption        "assumption A2 is class C"
lint_fails change-outside-files      "change 'backend/src/tagging/dto/create-tag.dto.ts' is outside T1's owned files" --graph "$EX/plan.json"
lint_fails bad-schema                "status 'finished' is not one of"
has "missing required key \"understanding\""
has "evidence[0]: \"exit_code\" must be an integer"

# the owned-files row is only checkable with the graph; without it the report is clean
python3 "$A" lint "$M/change-outside-files.md" >"$O" 2>&1; rc_is 0 $? "lint: owned-files row needs --graph"
python3 "$A" lint "$M/done-valid.md" --graph "$EX/plan.json" >"$O" 2>&1; no "outside"
sed 's/"task_id": "T1"/"task_id": "T42"/' "$M/done-valid.md" > "$TMP/t42.md"
python3 "$A" lint "$TMP/t42.md" --graph "$EX/plan.json" >"$O" 2>&1; rc_is 1 $? "lint: task id missing from the graph"
has "'T42' is not a task in the supplied plan"

# --- replay: a truthful report reproduces; a false claim is caught ---
python3 "$A" replay "$M/done-valid.md" --cwd "$EX" --yes >"$O" 2>&1; rc_is 0 $? "replay: truthful report passes"
has "2/2 reproduced"
python3 "$A" replay "$M/lying.md" --cwd "$EX" --yes >"$O" 2>&1; rc_is 1 $? "replay: claimed-0-actual-1 fails"
has "MISMATCH  \$ false"; has "claimed exit 0, actual 1"; has "actual output tail:"

# a command whose real exit is non-zero passes when that is what was claimed
cat > "$TMP/claims-1.json" <<'JSON'
{"agent": "qa-engineer", "task_id": "T3", "status": "failed", "understanding": "x",
 "inputs_read": [], "assumptions": [], "questions": [], "plan_issues": [], "decisions": [],
 "changes": [], "follow_ups": [],
 "evidence": [{"cmd": "echo boom; exit 1", "exit_code": 1, "output_tail": "boom"}]}
JSON
python3 "$A" replay "$TMP/claims-1.json" --cwd "$TMP" --yes >"$O" 2>&1; rc_is 0 $? "replay: an honest non-zero claim reproduces"

python3 - "$TMP" <<'PY'
import json, sys
r = json.load(open(sys.argv[1] + "/claims-1.json"))
r["evidence"] = [{"cmd": "sleep 5", "exit_code": 0, "output_tail": ""}]
json.dump(r, open(sys.argv[1] + "/slow.json", "w"))
PY
python3 "$A" replay "$TMP/slow.json" --cwd "$TMP" --timeout 1 --yes >"$O" 2>&1; rc_is 1 $? "replay: a timeout is a mismatch"
has "actual timeout"

# --- replay without --yes runs nothing ---
python3 - "$TMP" <<'PY'
import json, sys
r = json.load(open(sys.argv[1] + "/claims-1.json"))
r["status"] = "done"
r["evidence"] = [{"cmd": "touch created-by-replay", "exit_code": 0, "output_tail": ""}]
json.dump(r, open(sys.argv[1] + "/touch.json", "w"))
PY
python3 "$A" replay "$TMP/touch.json" --cwd "$TMP" >"$O" 2>&1; rc_is 3 $? "replay: without --yes exits 3"
[ ! -e "$TMP/created-by-replay" ] && ok "replay: without --yes nothing ran" || bad "replay: ran a command without --yes"
has "touch created-by-replay"
python3 "$A" replay "$TMP/touch.json" --cwd "$TMP" --yes >"$O" 2>&1; rc_is 0 $? "replay: --yes runs it"
[ -e "$TMP/created-by-replay" ] && ok "replay: --yes actually executed in --cwd" || bad "replay: --yes did not run in --cwd"

python3 "$A" replay "$M/done-no-evidence.md" --yes >"$O" 2>&1; rc_is 1 $? "replay: done with nothing to replay fails"

# --- summary: one batch, blocking first, max five, deduplicated ---
python3 "$A" summary "$M/needs-decision.md" "$M/needs-decision-frontend.md" --json >"$O" 2>&1; rc_is 0 $? "summary: runs"
python3 - "$O" >"$TMP/sum.chk" 2>&1 <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
q = d["questions"]
assert len(q) == 5, f"batch of {len(q)}"
assert q[0]["blocking"] and q[0]["question"] == "May a tag label contain emoji?", q[0]
assert sorted(q[0]["from"]) == ["T1/backend-engineer", "T2/frontend-engineer"], q[0]["from"]
assert all(not x["blocking"] for x in q[1:])
assert len(d["deferred_questions"]) == 2
assert [p["blocking"] for p in d["plan_issues"]] == [True, False]
PY
[ $? -eq 0 ] && ok "summary: deduplicated, blocking first, capped at 5, 2 deferred, plan issues blocking-first" \
  || { bad "summary: batch shape"; cat "$TMP/sum.chk"; }
python3 "$A" summary "$M/done-valid.md" >"$O" 2>&1; rc_is 0 $? "summary: a report with nothing open"
has "Questions (0 of 0"; has "- none"

# --- blocked/failed must say why (§3) ---
base='"agent":"x","task_id":"T1","understanding":"u","inputs_read":[],"assumptions":[],"decisions":[],"changes":[],"follow_ups":[]'
printf '{%s,"status":"blocked","questions":[],"plan_issues":[],"evidence":[]}' "$base" >"$TMP/blk.json"
python3 "$A" lint "$TMP/blk.json" >"$O" 2>&1; [ $? -ne 0 ] && grep -q "blocked with no blocking" "$O" && ok "lint: blocked with nothing blocking is rejected" || bad "lint: blocked with nothing blocking"
printf '{%s,"status":"blocked","questions":[],"plan_issues":[{"id":"P1","issue":"i","impact":"m","proposal":"p","blocking":true}],"evidence":[]}' "$base" >"$TMP/blk2.json"
python3 "$A" lint "$TMP/blk2.json" >"$O" 2>&1; [ $? -eq 0 ] && ok "lint: blocked with a blocking plan issue passes" || bad "lint: blocked with a blocking plan issue"
printf '{%s,"status":"failed","questions":[],"plan_issues":[],"evidence":[]}' "$base" >"$TMP/fl.json"
python3 "$A" lint "$TMP/fl.json" >"$O" 2>&1; [ $? -ne 0 ] && grep -q "failed with no evidence" "$O" && ok "lint: failed without evidence is rejected" || bad "lint: failed without evidence"
printf '{%s,"status":"failed","questions":[],"plan_issues":[],"evidence":[{"cmd":"false","exit_code":1,"output_tail":""}]}' "$base" >"$TMP/fl2.json"
python3 "$A" lint "$TMP/fl2.json" >"$O" 2>&1; [ $? -eq 0 ] && ok "lint: failed with evidence passes" || bad "lint: failed with evidence"

echo
echo "agent_report: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
