#!/usr/bin/env bash
# work-continuity bench: transcript_metrics counts prompts, compactions, fork tokens and
# restated corrections on a seeded transcript, reports zeros on a clean one, and refuses a
# missing file; grade.py scores the resume bench's answers and counts a crashed run as wrong.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TM="$ROOT/bench/work-continuity/transcript_metrics.py"
GRADE="$ROOT/bench/work-continuity/resume/grade.py"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
check() { if eval "$2"; then PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; else FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; cat "$TMP/out" 2>/dev/null | head -8; fi; }
field() { python3 -c "import json,sys; r=json.load(open('$TMP/out'))[0]; print(eval(sys.argv[1]))" "$1"; }

user()  { printf '{"type":"user","message":{"content":%s}}\n' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$1")"; }
asst()  { printf '{"type":"assistant","message":{"id":"%s","usage":{"input_tokens":%s,"output_tokens":0}%s}}\n' "$1" "$2" "${3:-}"; }

echo "== transcript_metrics: seeded session"
S="$TMP/seeded.jsonl"
{
  user "build the comments feature"
  user "what is the status ??"
  user "fix it in the respective branch"
  user "go ahead"
  user "I don't understand"
  printf '{"type":"system","subtype":"compact_boundary"}\n'
  user "This session is being continued from a previous conversation that ran out of context."
  printf '{"type":"user","message":{"content":[{"type":"tool_result","content":"x"}]}}\n'
  asst m1 100 ',"content":[{"type":"tool_use","name":"Agent","input":{"subagent_type":"fork"}}]'
  asst m1 100
  asst m2 50
} > "$S"
mkdir -p "$TMP/seeded/subagents"
asst s1 300 > "$TMP/seeded/subagents/agent-a.jsonl"; echo '{"agentType":"fork"}' > "$TMP/seeded/subagents/agent-a.meta.json"
asst s2 100 > "$TMP/seeded/subagents/agent-b.jsonl"; echo '{"agentType":"general-purpose"}' > "$TMP/seeded/subagents/agent-b.meta.json"
python3 "$TM" "$S" --json > "$TMP/out" 2>&1; rc=$?
check "exits 0" "[ $rc -eq 0 ]"
check "counts 5 human prompts (not tool results or the injected summary)" "[ \"\$(field \"r['prompts']\")\" = 5 ]"
check "counts 1 compaction from the boundary marker" "[ \"\$(field \"r['compactions']\")\" = 1 ]"
check "dedupes tokens by message id (150 main)" "[ \"\$(field \"r['tokens_main']\")\" = 150 ]"
check "fork share = 300 / 550" "[ \"\$(field \"r['fork_token_share']\")\" = 0.545 ]"
check "M1 = (1 restated + 1 status) per 5 prompts = 40.0" "[ \"\$(field \"r['m1_restated_per_100']\")\" = 40.0 ]"
check "approval-only and confusion each counted once" "[ \"\$(field \"r['counts']['approval_only'], r['counts']['confusion']\")\" = '(1, 1)' ]"

echo "== transcript_metrics: clean session"
C="$TMP/clean.jsonl"
{ user "add pagination to the list endpoint"; user "use cursor pagination, max 100 per page"; asst c1 10; } > "$C"
python3 "$TM" "$C" --json > "$TMP/out" 2>&1
check "no false positives: every count is 0" "[ \"\$(field \"sum(r['counts'].values())\")\" = 0 ]"
check "no subagents: fork share 0" "[ \"\$(field \"r['fork_token_share']\")\" = 0.0 ]"

echo "== transcript_metrics: missing file"
python3 "$TM" "$TMP/nope.jsonl" > "$TMP/out" 2>&1; rc=$?
check "exits 2 on a missing transcript" "[ $rc -eq 2 ]"

echo "== resume grade.py"
R="$TMP/results"; mkdir -p "$R"
python3 - "$R" <<'PY'
import json, sys
good = {"q1": "feat/comments-backend", "q2": "No, PR #3 is on hold", "q3": "1. backend\n2. frontend\n3. settings",
        "q4": "RETIRED_USER_LABEL", "q5": "No, merge-only", "q6": "1 hour", "q7": "unknown"}
bad = {"q1": "integration", "q2": "yes", "q3": "frontend, backend", "q4": "unknown", "q5": "yes", "q6": "15 min", "q7": "alice"}
json.dump({"structured_output": good, "total_cost_usd": 0.05, "num_turns": 3, "duration_ms": 9000}, open(sys.argv[1] + "/brief-1.json", "w"))
json.dump({"structured_output": bad, "total_cost_usd": 0.06, "num_turns": 6, "duration_ms": 17000}, open(sys.argv[1] + "/none-1.json", "w"))
open(sys.argv[1] + "/none-2.json", "w").close()
PY
python3 "$GRADE" "$R" > "$TMP/out" 2>&1
check "grades a fully correct run 7 of 7 (multi-line merge order included)" "grep -q '^| brief | 1 | 7.0 |' '$TMP/out'"
check "counts confident-wrong answers (q1, q2, q5)" "grep -q '^| none | 2 | 0.0 | 0% | 0.0 | 0% | 1.5 |' '$TMP/out'"
check "a crashed (empty) run is graded, not a crash" "grep -q '^| none | 2 ' '$TMP/out'"
python3 "$GRADE" "$R" > "$TMP/out" 2>&1
check "re-grading ignores its own graded.json" "! grep -q '^| graded' '$TMP/out'"

echo "work_continuity_bench: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
