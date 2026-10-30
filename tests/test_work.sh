#!/usr/bin/env bash
# work.py and its hooks: events are write-once and uniquely named, set events merge,
# repo URLs normalise without keeping a token, secret-like text writes nothing, the
# brief keeps holds/PRs/privacy line under a budget, lookup works from a worktree, the
# SessionStart brief is silent off-workstream, the fork guard follows its policy, and
# nothing at all lands in the project repository (PRD X4).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(cd "$(mktemp -d)" && pwd -P)"; OUT="$(mktemp -d)"
trap 'rm -rf "$TMP" "$OUT"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-64s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "$1"; sed 's/^/       /' "$OUT/r.out" | head -12; }
W="$ROOT/bin/100x"
run() {
  local exp="$1" label="$2"; shift 2
  "$W" work "$@" >"$OUT/r.out" 2>&1; local got=$?
  [ "$got" -eq "$exp" ] && ok "$label" || bad "$label (exit exp=$exp got=$got)"
}
has()   { grep -qF -- "$1" "$OUT/r.out" && ok "  reports $1" || bad "  NOT reported: $1"; }
hasnt() { grep -qF -- "$1" "$OUT/r.out" && bad "  unexpectedly reports $1" || ok "  does not report $1"; }
count_events() { find "$REC" -name '*.json' -type f 2>/dev/null | wc -l | tr -d ' '; }

export HOME="$TMP/home" HUNDREDX_WORK_DIR="$TMP/rec"
export GIT_CONFIG_GLOBAL="$TMP/gitconfig" GIT_CONFIG_NOSYSTEM=1
unset CLAUDE_CODE_SESSION_ID HUNDREDX_WORK HUNDREDX_FORK_POLICY HUNDREDX_WORK_BACKUP_HINT
mkdir -p "$HOME"
REC="$HUNDREDX_WORK_DIR"
TOKEN="ghp_abcdefghijklmnopqrstuvwxyz0123"
REPO="$TMP/widgets"
git init -q "$REPO"
git -C "$REPO" -c user.email=t@example.test -c user.name=t commit -q --allow-empty -m init
git -C "$REPO" branch -q -M main
git -C "$REPO" remote add origin "https://x-access-token:$TOKEN@github.com/Acme/Widgets.git"
git -C "$REPO" branch -q feat/api
git -C "$REPO" worktree add -q "$TMP/wt-api" feat/api
REFS_BEFORE="$(git -C "$REPO" for-each-ref)"
CONFIG_BEFORE="$(git -C "$REPO" config --local --list)"
cd "$REPO" || exit 1

echo "== usage"
"$W" work --help >"$OUT/r.out" 2>&1 && ok "--help exits 0" || bad "--help"
has "brief"; has "release-hold"
run 2 "no subcommand is a usage error"
run 0 "list with no record dir" list
has "no workstreams"
[ ! -e "$REC" ] && ok "  list and brief never create the record dir" || bad "  record dir created by a read"

echo "== repo normalisation (in-process)"
python3 - "$ROOT/scripts" "$TOKEN" >"$OUT/r.out" 2>&1 <<'PY' && ok "every remote form -> host/owner/repo, credentials dropped" || bad "normalise_repo"
import sys; sys.path.insert(0, sys.argv[1]); import work
tok = sys.argv[2]
cases = {
    f"https://x-access-token:{tok}@github.com/Acme/Widgets.git": "github.com/acme/widgets",
    "git@github.com:acme/widgets.git": "github.com/acme/widgets",
    "ssh://git@gitlab.example.com:2222/grp/sub/proj.git": "gitlab.example.com/grp/sub/proj",
    "github.com/acme/widgets/": "github.com/acme/widgets",
    "https://github.com/acme/widgets": "github.com/acme/widgets",
}
for raw, want in cases.items():
    got = work.normalise_repo(raw)
    assert got == want, (raw, got)
for bad in ("widgets", "https://github.com/acme", "", "github.com/../x"):
    try:
        work.normalise_repo(bad)
    except work.WorkError as err:
        assert tok not in str(err)
        continue
    raise AssertionError(f"accepted {bad!r}")
PY

echo "== start, set merge"
run 0 "start with a token URL" start tagging --repo "$(git remote get-url origin)" \
  --pr 12:feat/api:backend --pr 13:feat/ui:frontend --goal "Ship tagging" \
  --merge-order 12,13 --convention "one layer per PR"
has "started tagging"
grep -rqF "$TOKEN" "$REC" && bad "  token stored in the record" || ok "  token never stored"
grep -rqF "x-access-token" "$REC" && bad "  userinfo stored" || ok "  userinfo never stored"
grep -rqF '"github.com/acme/widgets"' "$REC" && ok "  repo stored as host/owner/repo" || bad "  repo key"
F="$(find "$REC/tagging/events" -name '*.json' | head -1)"
basename "$F" | grep -qE '^[0-9]{8}T[0-9]{12}Z-cli-[0-9a-f]{6}\.json$' \
  && ok "  event name: <utc yyyymmddTHHMMSSffffffZ>-cli-<6 hex>.json" || bad "  event name $(basename "$F")"
python3 - "$F" >"$OUT/r.out" 2>&1 <<'PY' && ok "  event body: schema 1, type, ws, at, session" || bad "  event body"
import json, sys; e = json.load(open(sys.argv[1]))
assert e["schema"] == 1 and e["type"] == "set" and e["ws"] == "tagging" and e["session"] == "cli", e
assert e["at"].endswith("Z") and e["prs"][0] == {"number": 12, "branch": "feat/api", "role": "backend"}, e
PY
CLAUDE_CODE_SESSION_ID="abc-123/../x" "$W" work note "named by session" --ws tagging >/dev/null 2>&1
ls "$REC/tagging/events" | grep -qE -- '-abc-123x-[0-9a-f]{6}\.json$' \
  && ok "  session id from CLAUDE_CODE_SESSION_ID, path characters stripped" || bad "  session label"
[ "$(stat -f %Lp "$REC" 2>/dev/null || stat -c %a "$REC")" = "700" ] && ok "  record dir is 0700" || bad "  record dir mode"
run 0 "a later set merges" start tagging --pr 13:feat/ui-v2:frontend --pr 14:feat/docs:docs \
  --goal "Ship tagging v2" --merge-order 12,14,13 --convention "squash merges"
has "updated tagging"
run 0 "brief after merge" brief --ws tagging
has "**Goal:** Ship tagging v2"
! grep -qx '\*\*Goal:\*\* Ship tagging' "$OUT/r.out" && ok "  the earlier goal is replaced" || bad "  earlier goal still shown"
has '| #13 | `feat/ui-v2` | frontend |'; hasnt '`feat/ui`'
has '| #12 | `feat/api` | backend |'; has '| #14 | `feat/docs` | docs |'
has "**Merge order:** #12 → #14 → #13"
has "- one layer per PR"; has "- squash merges"
run 1 "merge order naming an unknown PR is refused" start tagging --merge-order 12,99
run 1 "a new workstream without --repo is refused" start other --pr 1:x:y
run 1 "a bad --pr spec is refused" start tagging --pr twelve:feat:x
run 1 "a path-like workstream name is refused" start ../evil --repo github.com/a/b

echo "== write-once naming (in-process)"
python3 - "$ROOT/scripts" >"$OUT/r.out" 2>&1 <<'PY' && ok "O_EXCL: an existing name is never overwritten; a collision retries" || bad "exclusive create"
import datetime, os, sys, tempfile, pathlib
sys.path.insert(0, sys.argv[1]); import work
d = pathlib.Path(tempfile.mkdtemp()); p = d / "x.json"
work.create_exclusive(p, "first")
try:
    work.create_exclusive(p, "second")
    raise AssertionError("overwrote an existing event")
except FileExistsError:
    pass
assert p.read_text() == "first"
link = d / "link.json"; os.symlink(d / "target", link)
try:
    work.create_exclusive(link, "x")
    raise AssertionError("wrote through a symlink")
except FileExistsError:
    pass
assert not (d / "target").exists()
os.environ["HUNDREDX_WORK_DIR"] = str(d / "rec")
fixed = datetime.datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=datetime.timezone.utc)
work.utc_now = lambda: fixed
seq = iter(["aaaaaa", "aaaaaa", "bbbbbb"])
work.secrets.token_hex = lambda n: next(seq)
a = work.write_event("ws1", "note", {"text": "one"})
b = work.write_event("ws1", "note", {"text": "two"})
assert a.name == "20260102T030405678901Z-cli-aaaaaa.json", a.name
assert b.name.endswith("-bbbbbb.json") and a != b
assert '"one"' in a.read_text() and '"two"' in b.read_text()
PY
N0="$(count_events)"
for i in $(seq 1 12); do "$W" work note "parallel note $i" --ws tagging >/dev/null 2>&1 & done; wait
[ "$(count_events)" -eq $((N0 + 12)) ] && ok "12 concurrent notes -> 12 distinct files" || bad "concurrent appends ($N0 -> $(count_events))"

echo "== secret refusal writes nothing"
N0="$(count_events)"
run 1 "a GitHub token in a note" note "deploy with $TOKEN" --ws tagging
has "looks like a secret"; hasnt "$TOKEN"
run 1 "an email address in a handoff" handoff "ping jane.doe@example.com tomorrow" --ws tagging
run 1 "password=... in a decision" decide "password = hunter2hunter2xx" --ws tagging
run 1 "a private key in a hold reason" hold 12 --reason "-----BEGIN RSA PRIVATE KEY-----" --ws tagging
run 1 "a token in a convention" start tagging --convention "use AKIAABCDEFGHIJKLMNOP"
[ "$(count_events)" -eq "$N0" ] && ok "  no event file written by any refusal" || bad "  a refused event was written"
run 0 "ordinary text with an @ handle is accepted" note "asked @reviewer about pagination" --ws tagging

echo "== decisions, holds, handoff, brief"
run 0 "decide with an id" decide "cursor pagination" --id D1 --ws tagging
run 0 "re-decide the same id" decide "keyset pagination" --id D1 --ws tagging
run 1 "a bad decision id is refused" decide "x" --id "bad id" --ws tagging
run 0 "hold 13" hold 13 --reason "waiting on design review" --ws tagging
run 1 "hold on a PR not in the workstream" hold 77 --reason x --ws tagging
run 0 "hold 14" hold 14 --reason "blocked on 13" --ws tagging
run 0 "release-hold 14" release-hold 14 --ws tagging
run 1 "release-hold with no active hold" release-hold 14 --ws tagging
run 0 "handoff" handoff "next: wire the UI to the cursor" --ws tagging
run 0 "brief" brief --ws tagging
has "Private to you: never quote this brief in commits, PR text or review comments."
has "- #13: waiting on design review"; hasnt "blocked on 13"
has "- D1: keyset pagination"; hasnt "cursor pagination"
has "handoff: next: wire the UI to the cursor"
has "read it live"
run 1 "brief for an unknown workstream" brief --ws nope

echo "== budget trimming"
for i in $(seq 1 9); do
  "$W" work note "long note $i $(printf 'x%.0s' $(seq 1 300))" --ws tagging >/dev/null 2>&1
done
run 0 "brief --max-tokens 400" brief --ws tagging --max-tokens 400
python3 - "$OUT/r.out" 400 <<'PY' && ok "  brief fits the token budget (len/4)" || bad "  brief over budget"
import sys; t = open(sys.argv[1]).read(); assert len(t) / 4 <= int(sys.argv[2]), len(t) / 4
PY
has "Private to you"; has "- #13: waiting on design review"
has '| #12 | `feat/api` | backend |'; has '| #14 | `feat/docs` | docs |'
has "long note 9"; hasnt "long note 1 "
has "older not shown"
run 0 "brief --max-tokens 1 still keeps holds, PRs and privacy" brief --ws tagging --max-tokens 1
has "Private to you"; has "- #13: waiting on design review"; has '| #13 |'

echo "== lookup from cwd and from a worktree"
run 1 "main branch maps to no workstream" note "orphan"
has "no workstream matches"
( cd "$TMP/wt-api" && "$W" work note "from the worktree" ) >"$OUT/r.out" 2>&1 \
  && ok "note from a worktree on feat/api resolves tagging" || bad "worktree lookup"
has "recorded in tagging"
( cd "$TMP/wt-api" && "$W" work brief ) >"$OUT/r.out" 2>&1 && ok "brief from the worktree" || bad "worktree brief"
has "from the worktree"
run 0 "list" list
has "tagging"

echo "== doctor"
run 0 "doctor without a backup" doctor
has "tagging:"; has "WARNING not backed up"
printf '.claude/projects union\n.config/100x/work union\n' > "$TMP/mirrors.txt"
HUNDREDX_WORK_DIR="$HOME/.config/100x/work" HUNDREDX_WORK_BACKUP_HINT="$TMP/mirrors.txt" \
  "$W" work doctor >"$OUT/r.out" 2>&1
has "backup: $TMP/mirrors.txt names it"; hasnt "not backed up"
printf '.config/100x/other union\n' > "$TMP/mirrors2.txt"
HUNDREDX_WORK_DIR="$HOME/.config/100x/work" HUNDREDX_WORK_BACKUP_HINT="$TMP/mirrors2.txt" \
  "$W" work doctor >"$OUT/r.out" 2>&1
has "WARNING not backed up"

echo "== HUNDREDX_WORK=off"
N0="$(count_events)"
HUNDREDX_WORK=off "$W" work note "while off" --ws tagging >"$OUT/r.out" 2>&1
[ "$(count_events)" -eq "$N0" ] && ok "off: note writes nothing" || bad "off: note wrote"
HUNDREDX_WORK=off "$W" work brief --ws tagging >"$OUT/r.out" 2>&1
hasnt "Private to you"

echo "== work_brief hook"
H="$ROOT/hooks/work_brief.py"
python3 "$H" < /dev/null >"$OUT/r.out" 2>&1; rc=$?
[ "$rc" -eq 0 ] && [ ! -s "$OUT/r.out" ] && ok "empty stdin: silent, exit 0" || bad "empty stdin (rc=$rc)"
echo 'not json' | python3 "$H" >"$OUT/r.out" 2>&1; rc=$?
[ "$rc" -eq 0 ] && [ ! -s "$OUT/r.out" ] && ok "malformed payload: silent, exit 0" || bad "malformed payload"
printf '{"cwd": "%s"}' "$REPO" | python3 "$H" >"$OUT/r.out" 2>&1
[ ! -s "$OUT/r.out" ] && ok "no matching workstream (main): silent" || bad "unmatched cwd printed"
printf '{"cwd": "%s"}' "$TMP" | python3 "$H" >"$OUT/r.out" 2>&1
[ ! -s "$OUT/r.out" ] && ok "outside any repo: silent" || bad "non-repo cwd printed"
printf '{"cwd": "%s", "source": "compact"}' "$TMP/wt-api" | python3 "$H" >"$OUT/r.out" 2>&1
python3 - "$OUT/r.out" <<'PY' && ok "matched worktree: brief as SessionStart additionalContext" || bad "matched hook output"
import json, sys; o = json.load(open(sys.argv[1]))["hookSpecificOutput"]
assert o["hookEventName"] == "SessionStart" and "Private to you" in o["additionalContext"], o
assert "| #12 |" in o["additionalContext"]
PY
printf '{"cwd": "%s"}' "$TMP/wt-api" | HUNDREDX_WORK=off python3 "$H" >"$OUT/r.out" 2>&1
[ ! -s "$OUT/r.out" ] && ok "HUNDREDX_WORK=off: silent" || bad "off still briefed"
printf '{"cwd": "%s"}' "$TMP/wt-api" | HUNDREDX_WORK_DIR="$TMP/missing" python3 "$H" >"$OUT/r.out" 2>&1
[ ! -s "$OUT/r.out" ] && [ ! -e "$TMP/missing" ] && ok "no record dir: silent, creates nothing" || bad "missing record dir"

echo "== fork guard"
G="$ROOT/hooks/work_fork_guard.py"
printf '{"type":"user","message":"hi"}\n' > "$TMP/plain.jsonl"
printf '{"type":"user"}\n{"type":"system","subtype":"compact_boundary"}\n{"type":"user"}\n' > "$TMP/compacted.jsonl"
fork() {  # fork <transcript> [subagent_type] [tool]: runs the guard, sets rc
  printf '{"tool_name":"%s","tool_input":{"subagent_type":"%s","prompt":"x"},"transcript_path":"%s"}' \
    "${3:-Agent}" "${2:-fork}" "$1" | python3 "$G" >"$OUT/r.out" 2>"$OUT/r.err"; rc=$?
}
fork "$TMP/plain.jsonl"
[ "$rc" -eq 0 ] && [ ! -s "$OUT/r.out" ] && [ ! -s "$OUT/r.err" ] && ok "fork without compaction: allowed silently" || bad "plain fork (rc=$rc)"
fork "$TMP/compacted.jsonl"
python3 - "$OUT/r.out" <<'PY' && [ "$rc" -eq 0 ] && ok "fork after compaction: warned (context added, not blocked)" || bad "warn (rc=$rc)"
import json, sys; o = json.load(open(sys.argv[1]))
c = o["hookSpecificOutput"]; assert c["hookEventName"] == "PreToolUse" and "100x work brief" in c["additionalContext"], o
assert "permissionDecision" not in c, c
PY
fork "$TMP/compacted.jsonl" fork Task
[ "$rc" -eq 0 ] && grep -q "100x work brief" "$OUT/r.out" && ok "Task tool name is matched too" || bad "Task tool"
fork "$TMP/compacted.jsonl" general-purpose
[ "$rc" -eq 0 ] && [ ! -s "$OUT/r.out" ] && ok "a non-fork subagent after compaction: allowed silently" || bad "non-fork"
HUNDREDX_FORK_POLICY=refuse fork "$TMP/compacted.jsonl"
[ "$rc" -eq 2 ] && grep -q "100x work brief" "$OUT/r.err" && ok "refuse (env): exit 2, message on stderr" || bad "refuse env (rc=$rc)"
mkdir -p "$HOME/.config/100x"
echo '{"fork_policy": "refuse"}' > "$HOME/.config/100x/work.json"
fork "$TMP/compacted.jsonl"
[ "$rc" -eq 2 ] && ok "refuse (work.json fork_policy)" || bad "refuse config (rc=$rc)"
HUNDREDX_FORK_POLICY=allow fork "$TMP/compacted.jsonl"
[ "$rc" -eq 0 ] && [ ! -s "$OUT/r.out" ] && ok "env allow overrides config refuse" || bad "env override (rc=$rc)"
echo '{"fork_policy": "allow"}' > "$HOME/.config/100x/work.json"
fork "$TMP/compacted.jsonl"
[ "$rc" -eq 0 ] && [ ! -s "$OUT/r.out" ] && ok "allow (work.json): silent" || bad "allow config"
echo 'not json' > "$HOME/.config/100x/work.json"
fork "$TMP/compacted.jsonl"
[ "$rc" -eq 0 ] && grep -q "100x work brief" "$OUT/r.out" && ok "unreadable work.json falls back to warn" || bad "bad config fallback"
HUNDREDX_WORK=off fork "$TMP/compacted.jsonl"
[ "$rc" -eq 0 ] && [ ! -s "$OUT/r.out" ] && ok "HUNDREDX_WORK=off: allowed silently" || bad "off"
fork "$TMP/does-not-exist.jsonl"
[ "$rc" -eq 0 ] && [ ! -s "$OUT/r.out" ] && ok "missing transcript: allowed silently" || bad "missing transcript (rc=$rc)"
for payload in 'not json' '[]' '{"tool_name":"Agent","tool_input":"fork"}' \
               '{"tool_name":"Agent","tool_input":{"subagent_type":"fork"},"transcript_path":7}'; do
  printf '%s' "$payload" | HUNDREDX_FORK_POLICY=refuse python3 "$G" >"$OUT/r.out" 2>&1; rc=$?
  [ "$rc" -eq 0 ] && [ ! -s "$OUT/r.out" ] && ok "malformed payload allowed: ${payload:0:40}" || bad "malformed: $payload (rc=$rc)"
done
python3 - "$ROOT/hooks" "$TMP/big.jsonl" >"$OUT/r.out" 2>&1 <<'PY' && ok "marker split across a read-chunk boundary is found" || bad "chunk boundary"
import sys; sys.path.insert(0, sys.argv[1]); import work_fork_guard as g
marker = b'{"subtype":"compact_boundary"}'
with open(sys.argv[2], "wb") as fh:
    fh.write(b"x" * (g.CHUNK - 10) + marker + b"\n")
assert g.compacted(sys.argv[2])
PY

echo "== registration"
python3 - "$ROOT/hooks/hooks.json" >"$OUT/r.out" 2>&1 <<'PY' && ok "hooks.json: work_brief on SessionStart, fork guard on Agent|Task" || bad "registration"
import json, sys; h = json.load(open(sys.argv[1]))["hooks"]
ss = [(g.get("matcher"), x) for g in h["SessionStart"] for x in g["hooks"]]
assert any(m == "startup|resume|clear|compact" and x["command"].endswith('/hooks/work_brief.py"')
           and "${CLAUDE_PLUGIN_ROOT}" in x["command"] and x["timeout"] == 10 for m, x in ss), ss
assert any(x["command"].endswith('/hooks/session_start.py"') for _, x in ss), ss
pt = [(g.get("matcher"), x) for g in h["PreToolUse"] for x in g["hooks"]]
assert any(m == "Agent|Task" and "work_fork_guard.py" in x["command"] for m, x in pt), pt
assert sum("require_verification.py" in x["command"] for _, x in pt) == 8, pt
PY

echo "== X4: nothing in the project repository"
cd "$TMP" || exit 1
[ -z "$(git -C "$REPO" status --porcelain)" ] && ok "git status --porcelain is empty in the repo" || bad "repo has changes"
[ -z "$(git -C "$TMP/wt-api" status --porcelain)" ] && ok "git status --porcelain is empty in the worktree" || bad "worktree has changes"
[ "$(git -C "$REPO" for-each-ref)" = "$REFS_BEFORE" ] && ok "git for-each-ref shows no new refs" || bad "refs changed"
[ "$(git -C "$REPO" config --local --list)" = "$CONFIG_BEFORE" ] && ok "repo git config unchanged" || bad "repo config changed"

echo
echo "work: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
