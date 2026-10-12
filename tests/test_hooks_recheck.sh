#!/usr/bin/env bash
# Regression suite for the re-check Stop hook (hooks/recheck_gate.py, skills/recheck).
# Run: bash tests/test_hooks_recheck.sh   Exits non-zero on any failure.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
HOOK="$ROOT/hooks/recheck_gate.py"
PROMPT_FILE="$ROOT/skills/recheck/references/recheck-prompt.md"
# A clean HOME and no mode override, so the user's own config cannot change a result.
export HOME="$TMP/home"; mkdir -p "$HOME"
unset HUNDREDX_RECHECK
export CLAUDE_PLUGIN_ROOT="$ROOT"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }

# fixture <name> <spec> : writes $TMP/<name>.jsonl in Claude Code's transcript shape.
# spec is a JSON list of steps: ["user", text] | ["meta", text] | ["text", text] |
# ["tool", name, input] (an assistant tool_use followed by its user tool_result).
fixture() {
  python3 - "$TMP/$1.jsonl" "$2" <<'PY'
import json, sys
out, steps = sys.argv[1], json.loads(sys.argv[2])
rows, n = [], 0
def base(kind, **kw):
    global n; n += 1
    d = {"type": kind, "uuid": f"u{n}", "sessionId": "s", "isSidechain": False,
         "timestamp": "2026-10-12T00:00:00Z", "cwd": "/repo"}
    d.update(kw); return d
for s in steps:
    if s[0] in ("user", "meta"):
        rows.append(base("user", isMeta=(s[0] == "meta"),
                         message={"role": "user", "content": s[1]}))
    elif s[0] == "text":
        rows.append(base("assistant", message={"id": f"m{n}", "role": "assistant",
                    "model": "claude", "content": [{"type": "text", "text": s[1]}]}))
    elif s[0] == "tool":
        tid = f"toolu_{n}"
        rows.append(base("assistant", message={"id": f"m{n}", "role": "assistant",
                    "content": [{"type": "tool_use", "id": tid, "name": s[1], "input": s[2]}]}))
        rows.append(base("user", message={"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": tid, "content": "ok"}]},
                    toolUseResult={"type": "text"}))
    elif s[0] == "side":     # a subagent's entry: never part of the main turn
        rows.append(base("assistant", isSidechain=True, message={"role": "assistant",
                    "content": [{"type": "tool_use", "id": "x", "name": "Edit", "input": {}}]}))
rows.insert(0, {"type": "summary", "summary": "earlier work", "leafUuid": "u0"})
with open(out, "w") as f:
    f.write("\n".join(json.dumps(r) for r in rows) + "\n")
PY
}
# stop <transcript> [stop_hook_active] : the hook's raw stdout
stop() {
  python3 -c 'import json,sys; print(json.dumps({"hook_event_name":"Stop","session_id":"s","transcript_path":sys.argv[1],"cwd":"/repo","stop_hook_active":sys.argv[2]=="true"}))' \
    "$1" "${2:-false}" | python3 "$HOOK"
}
decision() { stop "$@" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("decision") or "none")'; }
expect() { # expect <want> <label> <fixture> [active]
  local got; got="$(decision "$TMP/$3.jsonl" "${4:-false}")"
  [ "$got" = "$1" ] && ok "$2" || bad "$2 (want=$1 got=$got)"
}

LONG="$(python3 -c 'print("The migration plan, step by step. " * 60)')"
EDIT='["tool","Edit",{"file_path":"/repo/app.py","old_string":"a","new_string":"b"}]'
fixture edit       '[["user","earlier question"],["text","earlier answer"],["user","fix the parser"],["tool","Read",{"file_path":"/repo/app.py"}],'"$EDIT"',["text","Fixed."]]'
fixture long       "$(python3 -c 'import json,sys; print(json.dumps([["user","plan the migration"],["text",sys.argv[1]]]))' "$LONG")"
fixture short      '[["user","fix the parser"],'"$EDIT"',["text","Fixed."],["user","what does -n do in grep?"],["text","It prints line numbers."]]'
fixture readonly   '[["user","where is auth handled?"],["tool","Grep",{"pattern":"auth"}],["tool","Read",{"file_path":"/repo/auth.py"}],["text","In auth.py."]]'
fixture notebook   '[["user","update the notebook"],["tool","NotebookEdit",{"notebook_path":"/repo/a.ipynb"}],["text","Done."]]'
fixture done       '[["user","fix it"],'"$EDIT"',["text","Fixed.\n\nRe-check: no changes — verified the callers"]]'
fixture done_bold  '[["user","fix it"],'"$EDIT"',["text","Fixed.\n**Re-check:** cut the extra helper"]]'
fixture cmd        '[["user","fix it"],'"$EDIT"',["text","Fixed."],["user","<command-name>/100x:recheck</command-name>"],["meta","Base directory for this skill: /plugin/skills/recheck"],'"$EDIT"',["text","Fixed again."]]'
fixture pasted     '[["user","fix it"],'"$EDIT"',["text","Fixed."],["user","Before you finish: assume this answer still has at least one mistake."],'"$EDIT"',["text","Fixed again."]]'
fixture skilltool  '[["user","double-check that"],["tool","Skill",{"skill":"100x:recheck"}],'"$EDIT"',["text","Fixed again."]]'
fixture meta_mid   '[["user","fix the parser"],'"$EDIT"',["meta","<local-command-stdout>ok</local-command-stdout>"],["text","Fixed."]]'
fixture sidechain  '[["user","ask an agent"],["tool","Task",{"prompt":"x"}],["side"],["text","The agent finished."]]'

fixture bash_sed   '[["user","bump it"],["tool","Bash",{"command":"sed -i.bak s/a/b/ app.py"}],["text","Bumped."]]'
fixture bash_redir '[["user","write it"],["tool","Bash",{"command":"cat > notes.md <<EOF\nx\nEOF"}],["text","Written."]]'
fixture bash_commit '[["user","commit"],["tool","Bash",{"command":"git add -A && git commit -m x"}],["text","Committed."]]'
fixture bash_read  '[["user","check"],["tool","Bash",{"command":"git status 2>&1 | head > /dev/null; ls -la"}],["text","Clean."]]'

echo "--- decisions"
expect block "edit turn blocks with the prompt"                     edit
expect block "long text answer (>= 1500 chars) blocks"               long
expect none  "short Q&A after an earlier edit turn: no block"        short
expect block "Bash sed -i counts as an edit"                         bash_sed
expect block "Bash redirect to a file counts as an edit"             bash_redir
expect block "Bash git commit counts as an edit"                     bash_commit
expect none  "read-only Bash (2>&1, >/dev/null) is not an edit"      bash_read
expect none  "read-only tools and a short answer: no block"          readonly
expect block "NotebookEdit counts as an edit"                        notebook
expect none  "stop_hook_active: never loops"                         edit true
expect none  "answer already ends with a Re-check: line"             done
expect none  "Re-check: line in markdown bold also counts"           done_bold
expect none  "user invoked /100x:recheck this turn"                  cmd
expect none  "user pasted the re-check prompt this turn"             pasted
expect none  "recheck skill invoked through the Skill tool"          skilltool
expect block "an isMeta user entry does not end the turn"            meta_mid
expect none  "a subagent's (sidechain) edit is not this turn's"      sidechain

echo "--- prompt"
python3 - "$PROMPT_FILE" "$(stop "$TMP/edit.jsonl")" <<'PY' && ok "reason equals the references file's marked block" || bad "reason equals the references file"
import json, sys
text = open(sys.argv[1], encoding="utf-8").read()
body = text.split("<!-- recheck-prompt:start -->")[1].split("<!-- recheck-prompt:end -->")[0]
want = "\n".join(l for l in body.strip().splitlines() if not l.startswith("```")).strip()
got = json.loads(sys.argv[2])["reason"]
assert got == want, (got, want)
assert got.startswith("Before you finish: assume this answer still has at least one mistake."), got
assert got.splitlines()[-1].startswith('"Re-check: <what changed>"'), got
PY
got="$(cd "$TMP" && env -u CLAUDE_PLUGIN_ROOT python3 "$HOOK" <<<'{"transcript_path":"'"$TMP/edit.jsonl"'"}' \
       | python3 -c 'import json,sys; print(json.load(sys.stdin).get("decision"))')"
[ "$got" = "block" ] && ok "no CLAUDE_PLUGIN_ROOT: prompt found beside the script" || bad "fallback prompt location (got=$got)"
got="$(CLAUDE_PLUGIN_ROOT="$TMP/nowhere" decision "$TMP/edit.jsonl")"
[ "$got" = "block" ] && ok "stale CLAUDE_PLUGIN_ROOT: falls back to the script's plugin" || bad "stale plugin root (got=$got)"

echo "--- config"
got="$(HUNDREDX_RECHECK=off decision "$TMP/edit.jsonl")"
[ "$got" = "none" ] && ok "HUNDREDX_RECHECK=off: no block" || bad "env off (got=$got)"
mkdir -p "$HOME/.config/100x"
printf '{"mode": "manual"}\n' > "$HOME/.config/100x/recheck.json"
expect none  "config mode manual: no block"                          edit
got="$(HUNDREDX_RECHECK=auto decision "$TMP/edit.jsonl")"
[ "$got" = "block" ] && ok "env auto overrides config manual" || bad "env overrides config (got=$got)"
printf '{"mode": "auto", "min_chars": 100000}\n' > "$HOME/.config/100x/recheck.json"
expect none  "min_chars raised: long answer no longer blocks"        long
expect block "min_chars does not exempt an edit"                     edit
printf '{"mode": "auto", "min_chars": 5}\n' > "$HOME/.config/100x/recheck.json"
expect block "min_chars lowered: a short answer blocks"              readonly
printf 'not json' > "$HOME/.config/100x/recheck.json"
expect block "unreadable config: defaults (auto)"                    edit
got="$(HUNDREDX_RECHECK=bogus decision "$TMP/edit.jsonl")"
[ "$got" = "block" ] && ok "unknown env mode is ignored" || bad "unknown env mode (got=$got)"
rm -f "$HOME/.config/100x/recheck.json"

echo "--- last_assistant_message"
# The host's transcript can lag the turn; the payload's last message decides length/Re-check.
lam() { # lam <fixture> <message> : decision for a Stop carrying last_assistant_message
  python3 -c 'import json,sys; print(json.dumps({"hook_event_name":"Stop","transcript_path":sys.argv[1],"last_assistant_message":sys.argv[2]}))' \
    "$TMP/$1.jsonl" "$2" | python3 "$HOOK" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("decision") or "none")'
}
got="$(lam readonly "$LONG")"
[ "$got" = "block" ] && ok "long last_assistant_message not yet in the transcript blocks" || bad "lagging transcript (got=$got)"
got="$(lam edit "Fixed.
Re-check: no changes — verified the callers")"
[ "$got" = "none" ] && ok "Re-check: line in last_assistant_message counts" || bad "Re-check in payload (got=$got)"

echo "--- SubagentStop"
# Claude Code's on-disk layout: <session>.jsonl plus <session>/subagents/agent-<id>.jsonl
# (+ .meta.json with agentType), every subagent entry isSidechain with its agentId.
SESS="$TMP/sess"; mkdir -p "$SESS/subagents"
fixture main_q '[["user","run the backend agent"],["tool","Task",{"subagent_type":"100x:backend-engineer"}],["text","The agent finished."]]'
cp "$TMP/main_q.jsonl" "$SESS.jsonl"
python3 - "$TMP/edit.jsonl" "$SESS/subagents/agent-a1.jsonl" "$TMP/sub_short.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if '"summary"' not in l[:30]]
for r in rows:
    r.update(isSidechain=True, agentId="a1")
open(sys.argv[2], "w").write("".join(json.dumps(r) + "\n" for r in rows))
short = [{"type": "user", "isSidechain": True, "agentId": "a2", "message": {"role": "user", "content": "list files"}},
         {"type": "assistant", "isSidechain": True, "agentId": "a2", "message": {"role": "assistant", "content": [{"type": "text", "text": "a.py"}]}}]
open(sys.argv[3], "w").write("".join(json.dumps(r) + "\n" for r in short))
PY
printf '{"agentType":"100x:backend-engineer"}\n' > "$SESS/subagents/agent-a1.meta.json"
sub() { # sub <agent_type or -> [agent_transcript_path] [stop_hook_active]: decision
  python3 -c '
import json, sys
d = {"hook_event_name": "SubagentStop", "session_id": "sess", "transcript_path": sys.argv[1],
     "agent_id": "a1", "stop_hook_active": sys.argv[4] == "true"}
if sys.argv[2] != "-": d["agent_type"] = sys.argv[2]
if sys.argv[3]: d["agent_transcript_path"] = sys.argv[3]
print(json.dumps(d))' "$SESS.jsonl" "$1" "${2:-}" "${3:-false}" \
  | python3 "$HOOK" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("decision") or "none")'
}
sub_expect() { local want="$1" label="$2"; shift 2; local got; got="$(sub "$@")"
  [ "$got" = "$want" ] && ok "$label" || bad "$label (want=$want got=$got)"; }
sub_expect none  "SubagentStop, default config (subagents off): no block"  100x:backend-engineer
printf '{"subagents": "all"}\n' > "$HOME/.config/100x/recheck.json"
sub_expect block "subagents all: subagent's edit turn blocks (derived transcript)" 100x:backend-engineer
sub_expect none  "subagents all: stop_hook_active never loops"           100x:backend-engineer "" true
sub_expect none  "subagents all: agent_transcript_path wins (short Q&A)"  100x:backend-engineer "$TMP/sub_short.jsonl"
got="$(HUNDREDX_RECHECK=off sub 100x:backend-engineer)"
[ "$got" = "none" ] && ok "mode off also disables SubagentStop" || bad "mode off subagents (got=$got)"
printf '{"subagents": ["100x:backend-engineer", "Explore"]}\n' > "$HOME/.config/100x/recheck.json"
sub_expect block "allowlist: matching agent_type blocks"                 100x:backend-engineer
sub_expect none  "allowlist: other agent_type does not"                  general-purpose
sub_expect block "allowlist: agent type read from .meta.json when absent" -
printf '{"subagents": ["backend-engineer"]}\n' > "$HOME/.config/100x/recheck.json"
sub_expect block "allowlist: bare name matches a plugin-prefixed type"   100x:backend-engineer
got="$(HUNDREDX_RECHECK_SUBAGENTS=off sub 100x:backend-engineer)"
[ "$got" = "none" ] && ok "HUNDREDX_RECHECK_SUBAGENTS=off overrides the config" || bad "env subagents off (got=$got)"
rm -f "$HOME/.config/100x/recheck.json"
got="$(HUNDREDX_RECHECK_SUBAGENTS=Explore,general-purpose sub general-purpose)"
[ "$got" = "block" ] && ok "HUNDREDX_RECHECK_SUBAGENTS comma list allows a type" || bad "env subagents list (got=$got)"
got="$(HUNDREDX_RECHECK_SUBAGENTS=all sub - "$TMP/missing.jsonl" | tr -d '\n')"
[ "$got" = "block" ] && ok "missing agent_transcript_path: falls back to the derived file" || bad "fallback transcript (got=$got)"
# Legacy layout: sidechain entries inside the main transcript; the main turn's own edit
# must not count for the subagent, and the subagent's must not count for the main stop.
fixture legacy '[["user","ask an agent"],["tool","Task",{"prompt":"x"}],["side"],["text","The agent finished."]]'
got="$(python3 -c 'import json,sys; print(json.dumps({"hook_event_name":"SubagentStop","transcript_path":sys.argv[1],"agent_id":"zz"}))' "$TMP/legacy.jsonl" \
  | HUNDREDX_RECHECK_SUBAGENTS=all python3 "$HOOK" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("decision") or "none")')"
[ "$got" = "block" ] && ok "legacy layout: subagent judged on its sidechain entries" || bad "legacy sidechain (got=$got)"

echo "--- fail-open"
out="$(printf 'garbage' | python3 "$HOOK" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && [ "$out" = "{}" ] && ok "malformed stdin: {} exit 0" || bad "malformed stdin (rc=$rc out=$out)"
out="$(stop "$TMP/missing.jsonl")"
[ "$out" = "{}" ] && ok "missing transcript: {}" || bad "missing transcript ($out)"
printf '{"type":"user"\n\0\0garbage\n' > "$TMP/broken.jsonl"
out="$(stop "$TMP/broken.jsonl")"; rc=$?
[ "$rc" -eq 0 ] && [ "$out" = "{}" ] && ok "corrupt transcript lines: {}" || bad "corrupt transcript ($out)"
out="$(printf '[1,2]' | python3 "$HOOK")"
[ "$out" = "{}" ] && ok "non-object stdin: {}" || bad "non-object stdin ($out)"

echo "--- performance"
python3 - "$TMP/big.jsonl" <<'PY'
import json, sys
filler = "x" * 900
# Worst case: one turn of ~3 MB of tool calls, so the whole 2 MB tail is parsed.
with open(sys.argv[1], "w") as f:
    f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "fix it"}}) + "\n")
    f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t", "name": "Write", "input": {"file_path": "/r/a"}}]}}) + "\n")
    for i in range(3000):
        f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": f"r{i}", "name": "Read", "input": {"file_path": filler}}]}}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"r{i}", "content": filler}]}}) + "\n")
    f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "w", "name": "Edit", "input": {"file_path": "/r/a"}}]}}) + "\n")
PY
ms="$(python3 - "$HOOK" "$TMP/big.jsonl" <<'PY'
import json, subprocess, sys, time
t = time.time()
out = subprocess.run([sys.executable, sys.argv[1]], input=json.dumps({"transcript_path": sys.argv[2]}),
                     capture_output=True, text=True).stdout
assert json.loads(out).get("decision") == "block", out
print(int((time.time() - t) * 1000))
PY
)"
[ -n "$ms" ] && [ "$ms" -lt 1000 ] && ok "3 MB transcript decided in ${ms}ms (< 1s, tail read only)" || bad "performance (${ms:-error}ms)"

echo "--- registration"
python3 - "$ROOT/hooks/hooks.json" <<'PY' && ok "Stop runs stop_gate then recheck_gate via CLAUDE_PLUGIN_ROOT" || bad "hook registration"
import json, sys
cmds = [x["command"] for g in json.load(open(sys.argv[1]))["hooks"]["Stop"] for x in g["hooks"]]
i = [n for n, c in enumerate(cmds) if "${CLAUDE_PLUGIN_ROOT}/hooks/stop_gate.py" in c]
j = [n for n, c in enumerate(cmds) if "${CLAUDE_PLUGIN_ROOT}/hooks/recheck_gate.py" in c]
assert len(i) == 1 and len(j) == 1 and i[0] < j[0], cmds
PY
python3 - "$ROOT/hooks/hooks.json" <<'PY' && ok "SubagentStop runs recheck_gate via CLAUDE_PLUGIN_ROOT" || bad "SubagentStop registration"
import json, sys
cmds = [x["command"] for g in json.load(open(sys.argv[1]))["hooks"]["SubagentStop"] for x in g["hooks"]]
assert any("${CLAUDE_PLUGIN_ROOT}/hooks/recheck_gate.py" in c for c in cmds), cmds
PY
grep -q 'references/recheck-prompt.md' "$ROOT/skills/recheck/SKILL.md" \
  && ok "SKILL.md points at the single prompt source" || bad "SKILL.md prompt source"

echo
echo "hooks-recheck: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
