#!/usr/bin/env bash
# Regression suite for scripts/session_alias.py: a name is created for the current
# session, repeating it is a no-op, a name owned by another session is refused, a bad
# name is refused, old ecc entries (summary-file paths) still resolve, the store is
# never truncated, and a ~/.cc-1 session resumes with its own config dir.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
SA="$ROOT/scripts/session_alias.py"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-70s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-70s\n' "$1"; [ -s "$OUT/c.out" ] && sed 's/^/       /' "$OUT/c.out" | head -10; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" "${2:-$OUT/c.out}" && ok "has: $1" || bad "missing: $1"; }
no()   { grep -qF -- "$1" "${2:-$OUT/c.out}" && bad "false positive: $1" || ok "absent: $1"; }

FAKE_HOME="$TMP/home"
CLAUDE="$FAKE_HOME/.claude/projects"
CC1="$FAKE_HOME/.cc-1/projects"
mkdir -p "$CLAUDE/-repo-a" "$CC1/-repo-b"
STORE="$FAKE_HOME/.claude/session-aliases.json"

CUR=aaaaaaaa-0000-0000-0000-00000000c0de
OTHER=bbbbbbbb-0000-0000-0000-0000deadbeef
CC1_SID=cccccccc-0000-0000-0000-0000cafef00d
printf '{"type":"summary"}\n{"type":"user","cwd":"/repo/a"}\n' > "$CLAUDE/-repo-a/$CUR.jsonl"
printf '{"type":"user","cwd":"/repo/a"}\n' > "$CLAUDE/-repo-a/$OTHER.jsonl"
printf '{"type":"user","cwd":"/repo/b"}\n' > "$CC1/-repo-b/$CC1_SID.jsonl"

# An existing store in ecc's format: one entry whose summary file ends in OTHER's last
# 8 hex characters, one whose session is gone.
cat > "$STORE" <<JSON
{
  "version": "1.0",
  "aliases": {
    "legacy-name": {"sessionPath": "/x/session-data/2026-10-01-deadbeef-session.tmp", "createdAt": "2026-10-01T00:00:00.000Z", "updatedAt": "2026-10-01T00:00:00.000Z", "title": null},
    "dead-name": {"sessionPath": "/x/session-data/2026-09-01-00000000-session.tmp", "createdAt": "2026-09-01T00:00:00.000Z", "updatedAt": "2026-09-01T00:00:00.000Z", "title": null}
  }
}
JSON
LEGACY_BEFORE="$(python3 -c "import json; print(json.dumps(json.load(open('$STORE'))['aliases']['legacy-name'], sort_keys=True))")"

sa() { HOME="$FAKE_HOME" python3 "$SA" "$@" >"$OUT/c.out" 2>&1; }

CLAUDE_CODE_SESSION_ID=$CUR sa set my-first-alias
rc_is 0 $? "set: creates an alias for the current session"
has "Alias created: my-first-alias -> $CUR"
python3 - "$STORE" "$CUR" <<'PY' && ok "set: entry carries sessionId and the session's cwd" || bad "set: entry fields wrong"
import json, sys
e = json.load(open(sys.argv[1]))["aliases"]["my-first-alias"]
assert e["sessionId"] == sys.argv[2] and e["cwd"] == "/repo/a", e
PY

CLAUDE_CODE_SESSION_ID=$CUR sa set my-first-alias
rc_is 0 $? "set again: same name, same session is a no-op"
has "Already aliased as: my-first-alias"

CLAUDE_CODE_SESSION_ID=$CUR sa set legacy-name
rc_is 1 $? "collision: a name owned by another session is refused"
has "COLLISION"

CLAUDE_CODE_SESSION_ID=$CUR sa set "Bad Name!"
rc_is 2 $? "bad name: uppercase and spaces are refused"
CLAUDE_CODE_SESSION_ID=$CUR sa set ../escape
rc_is 2 $? "bad name: a path is refused"

env -u CLAUDE_CODE_SESSION_ID HOME="$FAKE_HOME" python3 "$SA" set no-env >"$OUT/c.out" 2>&1
rc_is 2 $? "no session id: refused, nothing guessed"
CLAUDE_CODE_SESSION_ID=ffffffff-0000-0000-0000-000000000000 sa set no-transcript
rc_is 2 $? "unknown session: refused when no transcript exists"

python3 - "$STORE" "$LEGACY_BEFORE" <<'PY' && ok "store: old entries unchanged after writes" || bad "store: an old entry changed"
import json, sys
a = json.load(open(sys.argv[1]))["aliases"]
assert json.dumps(a["legacy-name"], sort_keys=True) == sys.argv[2]
assert set(a) == {"legacy-name", "dead-name", "my-first-alias"}, sorted(a)
PY
[ ! -e "$STORE.tmp" ] && ok "store: no temp file left behind" || bad "store: temp file left behind"

sa resolve legacy-name
rc_is 0 $? "resolve: old ecc entry resolves by its 8-character suffix"
has "claude --resume $OTHER"
has "cd /repo/a &&"
no "CLAUDE_CONFIG_DIR"

sa resolve dead-name
rc_is 1 $? "resolve: an entry whose transcript is gone exits 1"
sa resolve no-such-name
rc_is 1 $? "resolve: an unknown name exits 1"

CLAUDE_CODE_SESSION_ID=$CC1_SID sa set from-cc1
rc_is 0 $? "set: a ~/.cc-1 session can be aliased"
sa resolve from-cc1
has "CLAUDE_CONFIG_DIR=$FAKE_HOME/.cc-1 claude --resume $CC1_SID"
has "cd /repo/b &&"

sa list
rc_is 0 $? "list: exits 0"
has "my-first-alias"
has "UNRESOLVED (no transcript ends in 00000000)"
no "UNRESOLVED (no transcript ends in deadbeef)"

# A fresh machine with no store yet: set creates it.
rm -f "$STORE"
CLAUDE_CODE_SESSION_ID=$CUR sa set fresh-store
rc_is 0 $? "set: creates the store when none exists"
python3 -c "import json; assert json.load(open('$STORE'))['version'] == '1.0'" \
  && ok "store: new file uses version 1.0" || bad "store: new file has the wrong version"

HOME="$TMP/nohome" python3 "$SA" list >"$OUT/c.out" 2>&1
rc_is 2 $? "missing homes: exits 2 when no session directory exists"

echo
echo "session_alias: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
