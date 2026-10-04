#!/usr/bin/env bash
# Regression suite for scripts/agent_report.py: every row of the OPERATING-MODEL §3
# rejection table is detected, valid reports pass, extract takes the LAST json block,
# lint --graph checks the worktree's real changes and the declared verify commands,
# replay runs only declared verify commands (never a gated action) and nothing without --yes.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EX="$ROOT/examples/orchestration"
M="$EX/messages"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
A="$ROOT/scripts/agent_report.py"
P="$ROOT/scripts/plan_dag.py"
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

# the fence finder is one linear pass: 80KB of unclosed ```json fences is not a hang
python3 -c "print('\`\`\`json\n{' * 13000)" > "$TMP/fences.md"
python3 - "$A" "$TMP/fences.md" <<'PY'
import subprocess, sys, time
t = time.time()
subprocess.run([sys.executable, sys.argv[1], "extract", sys.argv[2]], capture_output=True)
sys.exit(0 if time.time() - t < 1.0 else 1)
PY
rc_is 0 $? "extract: 80KB of unclosed fences parses in under a second"

# --- lint: valid reports pass, as message or as bare JSON ---
for f in done-valid needs-decision needs-decision-frontend; do
  python3 "$A" lint "$M/$f.md" >"$O" 2>&1; rc_is 0 $? "lint: $f passes"
done
python3 "$A" lint "$TMP/r.json" >"$O" 2>&1; rc_is 0 $? "lint: accepts an extracted bare JSON report"
no "WARN"
# schema: a missing field is read as 1 with a warning; an unknown version is an error
python3 - "$TMP" <<'PY'
import json, sys
r = json.load(open(sys.argv[1] + "/r.json"))
del r["schema"]; json.dump(r, open(sys.argv[1] + "/noschema.json", "w"))
r["schema"] = 2; json.dump(r, open(sys.argv[1] + "/schema2.json", "w"))
PY
python3 "$A" lint "$TMP/noschema.json" >"$O" 2>&1; rc_is 0 $? "lint: a report without schema still lints"
has 'WARN  no "schema" field — read as schema 1'
python3 "$A" lint "$TMP/schema2.json" >"$O" 2>&1; rc_is 1 $? "lint: schema 2 is rejected"
has '"schema": 2 is not supported'

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
lint_fails bad-schema                "status 'finished' is not one of"
has "missing required key \"understanding\""
has "evidence[0]: \"exit_code\" must be an integer"

# --- lint --graph: the worktree, not the report, says what changed ---
python3 "$A" lint "$M/done-valid.md" --graph "$EX/plan.json" >"$O" 2>&1
rc_is 2 $? "lint --graph without --cwd is a usage error"
has "--graph needs --cwd"
WT="$TMP/wt"; mkdir -p "$WT"; cp "$EX/plan.json" "$WT/"
( cd "$WT" && git init -q && git config user.email e@e && git config user.name e \
  && git add -A && git commit -qm base )
BASE="$(git -C "$WT" rev-parse HEAD)"
lintg() { python3 "$A" lint "$1" --graph "$EX/plan.json" --cwd "$WT" "${@:2}" >"$O" 2>&1; }

# a hollow report: done, files claimed, nothing actually changed
lintg "$M/done-valid.md"; rc_is 1 $? "lint --graph: claimed changes that do not exist are rejected"
has "'backend/src/tagging/services/tag.service.ts' is claimed but the worktree has no change"
for f in needs-decision; do lintg "$M/$f.md"; rc_is 0 $? "lint --graph: $f on a clean worktree passes"; done

mkdir -p "$WT/backend/src/tagging/services"
echo 'export class TagService {}' > "$WT/backend/src/tagging/services/tag.service.ts"
echo 'export class TaggingModule {}' > "$WT/backend/src/tagging/tagging.module.ts"
lintg "$M/done-valid.md"; rc_is 0 $? "lint --graph: real changes inside owned files pass"
no "outside"; no "claimed but"
lintg "$M/needs-decision-frontend.md"; rc_is 1 $? "lint --graph: T1's files in T2's worktree are rejected"
has "the worktree changed 'backend/src/tagging/services/tag.service.ts', outside T2's owned files"

# an unreported edit outside the owned files is caught although the report omits it
mkdir -p "$WT/backend/src/tagging/dto"; echo x > "$WT/backend/src/tagging/dto/create-tag.dto.ts"
lintg "$M/done-valid.md"; rc_is 1 $? "lint --graph: an unreported change outside owned files"
has "the worktree changed 'backend/src/tagging/dto/create-tag.dto.ts', outside T1's owned files"
lintg "$M/change-outside-files.md"; rc_is 1 $? "lint --graph: a reported change outside owned files"
has "change 'backend/src/tagging/dto/create-tag.dto.ts' is outside T1's owned files"
rm -r "$WT/backend/src/tagging/dto"

# committed work: invisible against HEAD, seen against the task's base
( cd "$WT" && git add -A && git commit -qm work )
lintg "$M/done-valid.md"; rc_is 1 $? "lint --graph: committed work is not seen against HEAD"
lintg "$M/done-valid.md" --base "$BASE"; rc_is 0 $? "lint --graph --base: committed work since the base passes"
lintg "$M/done-valid.md" --base nope; rc_is 2 $? "lint --graph: an unknown --base is exit 2"
python3 "$A" lint "$M/done-valid.md" --graph "$EX/plan.json" --cwd "$TMP/none" >"$O" 2>&1
rc_is 2 $? "lint --graph: --cwd outside a git work tree is exit 2"

# done must carry every declared verify command, verbatim, with exit 0
python3 - "$TMP" <<'PY'
import json, sys
r = json.load(open(sys.argv[1] + "/r.json"))
r["evidence"] = [{"cmd": "true", "exit_code": 0, "output_tail": "all green"}]
json.dump(r, open(sys.argv[1] + "/hollow.json", "w"))
r["evidence"] = [{"cmd": "test -f plan.json", "exit_code": 0, "output_tail": ""}]
json.dump(r, open(sys.argv[1] + "/half.json", "w"))
PY
lintg "$TMP/hollow.json" --base "$BASE"; rc_is 1 $? "lint --graph: evidence that never ran the verify commands"
has "declared verify command 'test -f plan.json' is not in the evidence with exit 0"
lintg "$TMP/half.json" --base "$BASE"; rc_is 1 $? "lint --graph: one of two verify commands missing"
has "declared verify command 'python3 -c"
no "'test -f plan.json' is not in the evidence"

sed 's/"task_id": "T1"/"task_id": "T42"/' "$M/done-valid.md" > "$TMP/t42.md"
lintg "$TMP/t42.md"; rc_is 1 $? "lint: task id missing from the graph"
has "'T42' is not a task in the supplied plan"
# the saved report itself, inside the worktree, is not a change
cp "$TMP/r.json" "$WT/T1.json"
python3 "$A" lint "$WT/T1.json" --graph "$EX/plan.json" --cwd "$WT" --base "$BASE" >"$O" 2>&1
rc_is 0 $? "lint --graph: a report saved inside the worktree is not counted as a change"
rm "$WT/T1.json"
cp "$EX/plan.json" "$WT/plan-copy.json"
python3 "$A" lint "$M/done-valid.md" --graph "$WT/plan-copy.json" --cwd "$WT" --base "$BASE" >"$O" 2>&1
rc_is 0 $? "lint --graph: the plan file itself, inside the worktree, is not counted as a change"
rm "$WT/plan-copy.json"

# --- replay: only the plan's declared verify commands ever run ---
python3 "$A" replay "$M/done-valid.md" --cwd "$WT" --yes >"$O" 2>&1; rc_is 2 $? "replay: --graph is required"
has "--graph plan.json is required"
python3 "$A" replay "$M/done-valid.md" --graph "$EX/plan.json" --cwd "$WT" --yes >"$O" 2>&1
rc_is 0 $? "replay: a truthful report passes"
has "2/2 reproduced"
python3 "$A" replay "$M/lying.md" --graph "$EX/plan.json" --cwd "$EX" --yes >"$O" 2>&1
rc_is 1 $? "replay: claimed-0-actual-1 fails"
has "MISMATCH  \$ test -f backend/test/tagging.e2e-spec.ts"; has "claimed exit 0, actual 1"; has "actual output tail:"

# a task-local plan for the remaining replay cases
mkplan() { # mkplan <verify command>...
  python3 - "$TMP/p.json" "$@" <<'PY'
import json, sys
json.dump({"schema": 1, "feature": "f", "tasks": [{"id": "T1", "owner": "backend-engineer",
  "files": ["src/**"], "acceptance": ["AC-1"], "verify": sys.argv[2:]}]}, open(sys.argv[1], "w"))
PY
}
mkrep() { # mkrep <status> <json evidence list>
  printf '{"schema":1,"agent":"x","task_id":"T1","status":"%s","understanding":"u","inputs_read":[],"assumptions":[],"questions":[],"plan_issues":[],"decisions":[],"changes":[],"follow_ups":[],"evidence":%s}' "$1" "$2" > "$TMP/rep.json"
}
RP="$TMP/run"; mkdir -p "$RP"; ( cd "$RP" && git init -q && git config user.email e@e && git config user.name e && echo x > f && git add -A && git commit -qm i )
replay() { python3 "$A" replay "$TMP/rep.json" --graph "$TMP/p.json" --cwd "$RP" "$@" >"$O" 2>&1; }

# an undeclared command is listed, never run
mkplan "test -f f"
mkrep done '[{"cmd":"test -f f","exit_code":0},{"cmd":"touch pwned","exit_code":0}]'
replay --yes; rc_is 3 $? "replay: an undeclared evidence command makes it exit 3"
has "not replayed (undeclared)  \$ touch pwned"; has "1/1 reproduced"
[ ! -e "$RP/pwned" ] && ok "replay: the undeclared command did not run" || bad "replay: ran an undeclared command"

# the reviewers' repro: subagent-authored shell that commits and plants a file
mkrep done '[{"cmd":"test -f f","exit_code":0},{"cmd":"git commit -qam x --allow-empty && touch pwned","exit_code":0}]'
replay --yes; rc_is 3 $? "replay: an undeclared commit is not run"
[ ! -e "$RP/pwned" ] && [ "$(git -C "$RP" rev-list --count HEAD)" = 1 ] \
  && ok "replay: no commit made, no file planted" || bad "replay: the undeclared shell ran"
# even when a plan (unlinted) declares it, a gated action is refused
mkplan "git commit -q --allow-empty -m x" "sh -c 'git commit -q --allow-empty -m y; touch pwned'"
mkrep done '[{"cmd":"git commit -q --allow-empty -m x","exit_code":0},{"cmd":"sh -c '"'"'git commit -q --allow-empty -m y; touch pwned'"'"'","exit_code":0}]'
replay --yes; rc_is 3 $? "replay: a declared gated action is refused"
has "refused   \$ git commit -q --allow-empty -m x  — performs a gated action (git commit)"
has "refused   \$ sh -c"
[ ! -e "$RP/pwned" ] && [ "$(git -C "$RP" rev-list --count HEAD)" = 1 ] \
  && ok "replay: refused commands did not run" || bad "replay: a gated command ran"
python3 "$P" lint "$TMP/p.json" >"$O" 2>&1; rc_is 1 $? "plan_dag lint rejects the same gated verify commands"
has "performs a gated action (git commit)"

# the argv replay runs is screened, not the comment-stripped text plan_dag linted
mkplan "env A=1#x git tag -a v9 -m shipped"
mkrep done '[{"cmd":"env A=1#x git tag -a v9 -m shipped","exit_code":0}]'
replay --yes; rc_is 3 $? "replay: a gated action hidden behind a mid-word # is refused"
has "refused   \$ env A=1#x git tag -a v9 -m shipped"; has "gated action (git tag)"
[ -z "$(git -C "$RP" tag -l)" ] && ok "replay: no tag was created" || bad "replay: created a tag"
mkplan "sh -c 'env A=1#x git tag v8'"
mkrep done '[{"cmd":"sh -c '"'"'env A=1#x git tag v8'"'"'","exit_code":0}]'
replay --yes; rc_is 3 $? "replay: the same inside sh -c is refused"
[ -z "$(git -C "$RP" tag -l)" ] && ok "replay: no tag was created by the sh -c script" || bad "replay: sh -c created a tag"
mkplan "sh -c 'echo a#b; echo c # trailing comment'"
mkrep done '[{"cmd":"sh -c '"'"'echo a#b; echo c # trailing comment'"'"'","exit_code":0}]'
replay --yes; rc_is 0 $? "replay: a harmless # in a declared script still runs"
has "1/1 reproduced"

# a declared command that needs a shell but is not wrapped is refused, not mis-run
mkplan "test -f f && touch pwned"
mkrep done '[{"cmd":"test -f f && touch pwned","exit_code":0}]'
replay --yes; rc_is 3 $? "replay: unwrapped shell syntax is refused"
has "uses shell syntax '&&'"
[ ! -e "$RP/pwned" ] && ok "replay: the unwrapped command did not run" || bad "replay: ran unwrapped shell"

# sh -c is allowed when the plan declares it, and is shown before it runs
mkplan "sh -c 'echo boom; exit 1'"
mkrep failed '[{"cmd":"sh -c '"'"'echo boom; exit 1'"'"'","exit_code":1,"output_tail":"boom"}]'
replay; rc_is 3 $? "replay: without --yes exits 3"
has "runs a shell script: echo boom; exit 1"; has "Nothing has been run"
replay --yes; rc_is 0 $? "replay: an honest non-zero claim reproduces"

# a declared verify command with no evidence entry is a failure
mkplan "test -f f" "test -d ."
mkrep done '[{"cmd":"test -f f","exit_code":0}]'
replay --yes; rc_is 1 $? "replay: a declared command missing from the evidence fails"
has "MISSING   \$ test -d ."

# a timeout kills the whole process group, not just the shell
mkplan "sh -c '(sleep 2; touch late) & sleep 30'"
mkrep done '[{"cmd":"sh -c '"'"'(sleep 2; touch late) & sleep 30'"'"'","exit_code":0}]'
replay --timeout 1 --yes; rc_is 1 $? "replay: a timeout is a mismatch"
has "actual timeout"
python3 -c "import time; time.sleep(2.5)"
[ ! -e "$RP/late" ] && ok "replay: the timed-out command's children were killed" || bad "replay: a child outlived the timeout"

# without --yes nothing runs; with it, the declared command runs in --cwd
mkplan "touch created-by-replay"
mkrep done '[{"cmd":"touch created-by-replay","exit_code":0}]'
replay; rc_is 3 $? "replay: without --yes exits 3"
[ ! -e "$RP/created-by-replay" ] && ok "replay: without --yes nothing ran" || bad "replay: ran a command without --yes"
has "touch created-by-replay"
replay --yes; rc_is 0 $? "replay: --yes runs it"
[ -e "$RP/created-by-replay" ] && ok "replay: --yes actually executed in --cwd" || bad "replay: --yes did not run in --cwd"

python3 "$A" replay "$M/done-no-evidence.md" --graph "$EX/plan.json" --yes >"$O" 2>&1
rc_is 1 $? "replay: done with no evidence for the declared commands fails"

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
