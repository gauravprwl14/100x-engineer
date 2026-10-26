#!/usr/bin/env bash
# Regression suite for scripts/session_find.py: a session is found by keyword, the
# right one wins when several match, hook/system noise never counts as a hit, both
# default home directories (~/.claude and ~/.cc-1) are searched, and malformed input
# does not crash the scan.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
SF="$ROOT/scripts/session_find.py"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-70s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-70s\n' "$1"; [ -s "$OUT/c.out" ] && sed 's/^/       /' "$OUT/c.out" | head -10; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" "${2:-$OUT/c.out}" && ok "has: $1" || bad "missing: $1"; }
no()   { grep -qF -- "$1" "${2:-$OUT/c.out}" && bad "false positive: $1" || ok "absent: $1"; }

# Writes one JSONL record. Goes through python's json.dumps rather than a bash
# heredoc so quoting/escaping in message text can never corrupt the fixture.
write_line() {
  local file="$1" type="$2" content_json="$3" cwd="$4" ts="$5"
  python3 - "$file" "$type" "$content_json" "$cwd" "$ts" <<'PY'
import json, sys
file, typ, content_json, cwd, ts = sys.argv[1:6]
content = json.loads(content_json)
rec = {"type": typ, "message": {"role": typ, "content": content}, "cwd": cwd,
       "timestamp": ts, "sessionId": "x", "gitBranch": "main"}
with open(file, "a") as f:
    f.write(json.dumps(rec) + "\n")
PY
}
user_line()      { write_line "$1" user "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$3")" "$2" "2026-10-20T00:00:00.000Z"; }
assistant_text() { write_line "$1" assistant "$(python3 -c 'import json,sys; print(json.dumps([{"type":"text","text":sys.argv[1]}]))' "$3")" "$2" "2026-10-20T00:00:00.000Z"; }
noise_line()     { write_line "$1" hook_success "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$3")" "$2" "2026-10-20T00:00:00.000Z"; }

CLAUDE="$TMP/home-a/.claude/projects"
CC1="$TMP/home-b/.cc-1/projects"
mkdir -p "$CLAUDE/-proj-backend" "$CLAUDE/-proj-unrelated" "$CC1/-proj-frontend"

# Session 1 (.claude root): a real hit in a user turn.
S1="$CLAUDE/-proj-backend/11111111-0000-0000-0000-000000000001.jsonl"
user_line "$S1" "/repo/backend" "Let's design the tagging module repository layer."
touch -t 202510200900 "$S1"

# Session 2 (.cc-1 root): a real hit, in an assistant turn's text block, more recent
# than session 1 — must rank first.
S2="$CC1/-proj-frontend/22222222-0000-0000-0000-000000000002.jsonl"
assistant_text "$S2" "/repo/frontend" "Added the tagging module UI and wired it to the API."
touch -t 202510230900 "$S2"

# Session 3 (.claude root): the word only appears in hook/bookkeeping noise, never
# in a user/assistant turn — must NOT be reported (false-positive check).
S3="$CLAUDE/-proj-unrelated/33333333-0000-0000-0000-000000000003.jsonl"
noise_line "$S3" "/repo/unrelated" "ran hook for tagging module config sync"
user_line "$S3" "/repo/unrelated" "This session is about something else entirely."
touch -t 202510240900 "$S3"

# Session 4 (.claude root): oldest, also a real hit, plus a malformed trailing line —
# the scan must still find the valid hit instead of aborting on the garbage line.
S4="$CLAUDE/-proj-backend/44444444-0000-0000-0000-000000000004.jsonl"
user_line "$S4" "/repo/backend" "Early spike for the tagging module."
printf 'not valid json at all, still mentions tagging module\n' >> "$S4"
touch -t 202510010900 "$S4"

# Session 7 (.claude root): a real user turn, but the query only appears in the
# sibling `cwd` metadata field, never in the message content itself — must NOT be
# reported (metadata-field false positive, distinct from the hook-noise case above).
S7="$CLAUDE/-proj-unrelated/77777777-0000-0000-0000-000000000007.jsonl"
user_line "$S7" "/repo/tagging module/path" "This content is unrelated to the query."
touch -t 202510220900 "$S7"

BOTH_ROOTS="$CLAUDE,$CC1"

python3 "$SF" "tagging module" --roots "$BOTH_ROOTS" --json >"$OUT/c.out" 2>"$OUT/c.err"
rc_is 0 $? "found-case: exits 0 when sessions match"
python3 -c "import json,sys; json.load(open('$OUT/c.out'))" \
  && ok "found-case: --json output parses as JSON" || bad "found-case: --json output is not valid JSON"
has "22222222-0000-0000-0000-000000000002"
has "11111111-0000-0000-0000-000000000001"
has "44444444-0000-0000-0000-000000000004"
no  "33333333-0000-0000-0000-000000000003"
no  "77777777-0000-0000-0000-000000000007"

# Ranking: the most recently modified matching session (session 2, cc-1) must be
# first in the JSON array, the oldest (session 4) last.
FIRST_ID="$(python3 -c "import json; print(json.load(open('$OUT/c.out'))[0]['session_id'])")"
[ "$FIRST_ID" = "22222222-0000-0000-0000-000000000002" ] \
  && ok "ranking: most recently modified matching session is first" \
  || bad "ranking: expected session 2 first, got $FIRST_ID"
LAST_ID="$(python3 -c "import json; print(json.load(open('$OUT/c.out'))[-1]['session_id'])")"
[ "$LAST_ID" = "44444444-0000-0000-0000-000000000004" ] \
  && ok "ranking: oldest matching session is last" \
  || bad "ranking: expected session 4 last, got $LAST_ID"

# Both default home directories are represented in one run, each labelled correctly.
python3 -c "
import json
rows = json.load(open('$OUT/c.out'))
roots = {r['session_id']: r['root'] for r in rows}
assert roots['22222222-0000-0000-0000-000000000002'] == '.cc-1', roots
assert roots['11111111-0000-0000-0000-000000000001'] == '.claude', roots
" 2>"$OUT/py.err" \
  && ok "cross-root: .claude and .cc-1 sessions both found and labelled by root" \
  || bad "cross-root: root labelling wrong ($(cat "$OUT/py.err"))"

# Hit count is per-session, not per-byte: session 3's single real user turn about
# "something else" contributes zero hits for this query, and it correctly has none.
no "This session is about something else entirely"

# --limit truncates while keeping rank order.
python3 "$SF" "tagging module" --roots "$BOTH_ROOTS" --json --limit 2 >"$OUT/c.out" 2>&1
COUNT="$(python3 -c "import json; print(len(json.load(open('$OUT/c.out'))))")"
[ "$COUNT" = "2" ] && ok "limit: --limit 2 returns exactly 2 results" || bad "limit: expected 2 results, got $COUNT"

# A negative --limit is a usage error, not silently-wrong Python slice behaviour.
python3 "$SF" "tagging module" --roots "$BOTH_ROOTS" --limit -1 >"$OUT/c.out" 2>"$OUT/c.err"
rc_is 2 $? "negative limit: argparse usage error"

# --roots entries with surrounding whitespace are trimmed, not treated as a
# different (non-existent) path.
python3 "$SF" "tagging module" --roots " $CLAUDE , $CC1 " --json >"$OUT/c.out" 2>"$OUT/c.err"
rc_is 0 $? "roots with whitespace: still resolves both roots"
has "11111111-0000-0000-0000-000000000001"
has "22222222-0000-0000-0000-000000000002"

# Table (non-JSON) output carries the same session ids and a snippet line.
python3 "$SF" "tagging module" --roots "$BOTH_ROOTS" >"$OUT/c.out" 2>&1
rc_is 0 $? "table output: exits 0"
has "11111111-0000-0000-0000-000000000001"
has "[.claude]"
has "[.cc-1]"
has "tagging module"

# Case sensitivity: default is case-insensitive; --case-sensitive must miss a
# differently-cased query.
python3 "$SF" "TAGGING MODULE" --roots "$BOTH_ROOTS" --json >"$OUT/c.out" 2>&1
rc_is 0 $? "case-insensitive: default matches regardless of case"
python3 "$SF" "TAGGING MODULE" --roots "$BOTH_ROOTS" --case-sensitive >"$OUT/c.out" 2>&1
rc_is 1 $? "case-sensitive: --case-sensitive misses a differently-cased query"
has "No sessions found."

# No match at all: exit 1, not an error, with a clear message.
python3 "$SF" "no-such-topic-anywhere" --roots "$BOTH_ROOTS" >"$OUT/c.out" 2>&1
rc_is 1 $? "no-match case: exits 1"
has "No sessions found."

# Missing/empty roots: exit 2 (usage/environment error, distinct from "no match").
python3 "$SF" "tagging module" --roots "$TMP/does-not-exist/projects" >"$OUT/c.out" 2>"$OUT/c.err"
rc_is 2 $? "missing roots: exits 2 when no given root exists"
has "no session directory found" "$OUT/c.err"

# Empty query is a usage error, not a silent empty scan.
python3 "$SF" "   " --roots "$BOTH_ROOTS" >"$OUT/c.out" 2>"$OUT/c.err"
rc_is 2 $? "empty query: argparse usage error"

# Default roots actually resolve to ~/.claude/projects and ~/.cc-1/projects under
# $HOME, with no --roots flag at all — this is the behaviour the skill is for.
FAKE_HOME="$TMP/fakehome"
mkdir -p "$FAKE_HOME/.claude/projects/-proj" "$FAKE_HOME/.cc-1/projects/-proj"
S5="$FAKE_HOME/.claude/projects/-proj/55555555-0000-0000-0000-000000000005.jsonl"
S6="$FAKE_HOME/.cc-1/projects/-proj/66666666-0000-0000-0000-000000000006.jsonl"
user_line "$S5" "/repo/a" "default-root probe alpha"
user_line "$S6" "/repo/b" "default-root probe alpha"
HOME="$FAKE_HOME" python3 "$SF" "default-root probe alpha" --json >"$OUT/c.out" 2>"$OUT/c.err"
rc_is 0 $? "default roots: finds a match with no --roots, under a fake \$HOME"
has "55555555-0000-0000-0000-000000000005"
has "66666666-0000-0000-0000-000000000006"

# One of the two default homes missing entirely (no ~/.cc-1) must not break the scan.
rm -rf "$FAKE_HOME/.cc-1"
HOME="$FAKE_HOME" python3 "$SF" "default-root probe alpha" --json >"$OUT/c.out" 2>"$OUT/c.err"
rc_is 0 $? "default roots: still works when ~/.cc-1 does not exist"
has "55555555-0000-0000-0000-000000000005"

cd "$ROOT"
echo
echo "session_find: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
