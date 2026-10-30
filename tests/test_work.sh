#!/usr/bin/env bash
# work.py and its hooks: events are write-once and uniquely named, set events merge,
# repo URLs normalise without keeping a token, secret-like text writes nothing, the
# brief keeps holds/PRs/privacy line under a budget, lookup works from a worktree, the
# SessionStart brief is silent off-workstream, the fork guard follows its policy, doctor
# detects each defect it names (and nothing on a clean record) while writing nothing, and
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
unset CLAUDE_CONFIG_DIR HUNDREDX_CONFIG_DIRS
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
# doc [args...]: doctor --json from the current dir; sets drc, leaves the JSON in r.out.
doc() { "$W" work doctor --json "$@" >"$OUT/r.out" 2>&1; drc=$?; }
# sev <finding id>: the severities of that finding in the last doc run, or "none".
sev() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(" ".join(f["severity"] for f in d["findings"] if f["id"]==sys.argv[2]) or "none")' "$OUT/r.out" "$1" 2>/dev/null; }
expect() { local got; got="$(sev "$1")"; [ "$got" = "$2" ] && ok "  $1: $2" || bad "  $1: expected $2, got $got"; }
field() {  # field <finding id> <key>: that finding's text field
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print([f[sys.argv[3]] for f in d["findings"] if f["id"]==sys.argv[2]][0])' "$OUT/r.out" "$1" "$2" 2>/dev/null
}
gets_brief() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print([c["gets_brief"] for c in d["checks"] if c["id"]=="D-brief"][0])' "$OUT/r.out"; }
snapshot() {  # every path, size and mtime under the given dirs: doctor must change none
  python3 - "$@" <<'PY'
import os, sys
for top in sys.argv[1:]:
    for dirpath, dirs, files in os.walk(top):
        dirs.sort()
        for name in sorted(dirs + files):
            st = os.lstat(os.path.join(dirpath, name))
            print(os.path.join(dirpath, name), st.st_size, st.st_mtime_ns, oct(st.st_mode))
PY
}
# The backup repo the hint lives in; its upstream is a local ref, as doctor never fetches.
BK="$TMP/backup"
git init -q "$BK"
gc() { git -C "$BK" -c user.email=t@example.test -c user.name=t "$@"; }
printf '.claude/projects union\n%s union\n' "$REC" > "$BK/mirrors.txt"
gc add mirrors.txt; gc commit -q -m mirrors; git -C "$BK" branch -q -M main
git -C "$BK" remote add origin "$TMP/backup-remote.git"
git -C "$BK" update-ref refs/remotes/origin/main HEAD
git -C "$BK" branch -q --set-upstream-to=origin/main main
export HUNDREDX_WORK_BACKUP_HINT="$BK/mirrors.txt"
# A second record with every defect, so the clean record above stays clean.
R2="$TMP/rec2"; cp -Rp "$REC" "$R2"
E2="$R2/tagging/events"
printf '{"schema": 1, "type": "note", "tr' > "$E2/20200101T000000000000Z-cli-aaaaaa.json"
printf '{"schema": 2, "type": "note", "ws": "tagging", "at": "2020-01-01T00:00:00Z"}\n' \
  > "$E2/20200101T000000000001Z-cli-bbbbbb.json"
echo stray > "$E2/notes.txt"
mkdir -p "$R2/old/events"
printf '{"schema": 1, "type": "set", "ws": "old", "session": "cli", "at": "2020-01-01T00:00:00.000000Z", "repos": ["github.com/acme/widgets"], "prs": [{"number": 12, "branch": "feat/api", "role": "copy"}]}\n' \
  > "$R2/old/events/20200101T000000000000Z-cli-cccccc.json"
printf '{"schema": 1, "type": "hold", "ws": "old", "session": "cli", "at": "2020-01-02T00:00:00.000000Z", "pr": 12, "reason": "parked"}\n' \
  > "$R2/old/events/20200102T000000000000Z-cli-dddddd.json"
printf '{"schema": 1, "type": "handoff", "ws": "old", "session": "cli", "at": "2020-01-03T00:00:00.000000Z", "text": "first handoff"}\n' \
  > "$R2/old/events/20200103T000000000000Z-cli-eeeeee.json"
printf '{"schema": 1, "type": "note", "ws": "old", "session": "cli", "at": "2020-02-03T00:00:00.000000Z", "text": "a month later"}\n' \
  > "$R2/old/events/20200203T000000000000Z-cli-ffffff.json"
chmod 755 "$R2"
git -C "$REPO" -c advice.detachedHead=false worktree add -q --detach "$TMP/wt-detached" main
SNAP_BEFORE="$(snapshot "$REC" "$R2" "$BK" "$REPO")"

echo "-- clean: matched worktree, backed up, pushed, no stale holds"
cd "$TMP/wt-api" || exit 1
doc
[ "$drc" -eq 0 ] && ok "clean record: exit 0" || bad "clean record exit $drc"
python3 - "$OUT/r.out" >"$OUT/r.err" 2>&1 <<'PY' && ok "  --json: ok, findings, checks; every check ok; no finding" || { bad "  json shape"; sed 's/^/       /' "$OUT/r.err" | head -6; }
import json, sys; d = json.load(open(sys.argv[1]))
assert set(d) == {"ok", "findings", "checks"} and d["ok"] is True and d["findings"] == [], d
ids = [c["id"] for c in d["checks"]]
assert ids == ["D-record", "D-events", "D-lookup", "D-brief", "D-hooks", "D-backup", "D-holds"], ids
assert all(c["status"] == "ok" for c in d["checks"]), d["checks"]
PY
[ "$(gets_brief)" = "True" ] && ok "  hook dry run: a session here gets the brief" || bad "  dry run said no in a matched worktree"
"$W" work doctor >"$OUT/r.out" 2>&1
has "session brief here: yes"; has "-> tagging"; has "backup:       $BK/mirrors.txt"; has "no problems found"

echo "-- D-record"
HUNDREDX_WORK_DIR="$R2" doc
expect D-record.mode warn
field D-record.mode fix | grep -qF "chmod 700 $R2" && ok "  fix is chmod 700 <dir>" || bad "  mode fix"
[ "$drc" -eq 1 ] && ok "  a warning exits 1" || bad "  warning exit $drc"
HUNDREDX_WORK_DIR="$TMP/none" doc
expect D-record.missing info
field D-record.missing fix | grep -qF "100x work start" && ok "  fix is 100x work start" || bad "  missing fix"
[ ! -e "$TMP/none" ] && ok "  doctor did not create the record dir" || bad "  doctor created the record dir"
HUNDREDX_WORK=off doc
expect D-record.off warn
[ "$(gets_brief)" = "False" ] && ok "  off: dry run says no brief" || bad "  off: dry run said yes"
doc; expect D-record.mode none; expect D-record.off none

echo "-- D-events"
HUNDREDX_WORK_DIR="$R2" doc
expect D-events.unreadable warn; expect D-events.newer-schema warn; expect D-events.stray info
field D-events.unreadable what | grep -qF "20200101T000000000000Z-cli-aaaaaa.json" && ok "  names the unreadable file" || bad "  unreadable name"
field D-events.newer-schema fix | grep -qF "claude plugin install" && ok "  newer schema: fix upgrades the plugin" || bad "  newer fix"
doc; expect D-events.unreadable none; expect D-events.newer-schema none; expect D-events.stray none

echo "-- D-lookup"
doc --cwd "$TMP"
expect D-lookup.not-repo info
[ "$(gets_brief)" = "False" ] && ok "  outside a repo: dry run says no brief" || bad "  dry run said yes outside a repo"
doc --cwd "$REPO"
expect D-lookup.none info
field D-lookup.none what | grep -qF "tagging has this repo but not this branch" && ok "  names the workstream that has the repo" || bad "  near-match"
field D-lookup.none fix | grep -qF "100x work start tagging --pr <number>:main:<role>" && ok "  fix pre-fills workstream and branch" || bad "  none fix: $(field D-lookup.none fix)"
[ "$(gets_brief)" = "False" ] && ok "  unmatched branch: dry run says no brief" || bad "  dry run said yes on main"
HUNDREDX_WORK_DIR="$TMP/none" doc --cwd "$REPO"
field D-lookup.none fix | grep -qF -- "--repo github.com/acme/widgets --pr <number>:main:<role>" && ok "  no workstream at all: fix pre-fills the repo key" || bad "  repo fix: $(field D-lookup.none fix)"
HUNDREDX_WORK_DIR="$R2" doc
expect D-lookup.several warn
field D-lookup.several what | grep -qF "old, tagging" && ok "  names both workstreams" || bad "  several names"
[ "$(gets_brief)" = "False" ] && ok "  two matches: dry run says no brief" || bad "  dry run said yes on two matches"
git init -q "$TMP/no-origin"
doc --cwd "$TMP/no-origin"
expect D-lookup.no-origin warn
git -C "$TMP/no-origin" remote add origin https://github.com/acme/empty.git
doc --cwd "$TMP/no-origin"
expect D-lookup.detached info; expect D-lookup.bad-origin none
doc --cwd "$TMP/wt-detached"
expect D-lookup.detached info
doc; expect D-lookup.none none; expect D-lookup.several none

echo "-- D-brief"
R3="$TMP/rec3"
python3 - "$ROOT/scripts" "$R3" >"$OUT/r.out" 2>&1 <<'PY' || bad "seed a large workstream"
import os, sys; sys.path.insert(0, sys.argv[1]); os.environ["HUNDREDX_WORK_DIR"] = sys.argv[2]
import work
work.write_event("big", "set", {"repos": ["github.com/acme/widgets"],
                                "prs": [{"number": 12, "branch": "feat/api", "role": "api"}]})
for i in range(12):
    work.write_event("big", "decision", {"id": f"D{i}", "text": f"decision {i} " + "y" * 1500})
PY
HUNDREDX_WORK_DIR="$R3" doc
expect D-brief.budget warn
field D-brief.budget what | grep -qE "[1-9][0-9]* oldest decision" && ok "  says how many decisions are cut" || bad "  budget what"
[ "$(gets_brief)" = "True" ] && ok "  over budget: the hook still briefs" || bad "  budget: dry run said no"
doc; expect D-brief.budget none; expect D-brief.hook-silent none
python3 - "$ROOT/scripts" "$TMP/wt-api" >"$OUT/r.out" 2>&1 <<'PY' && ok "a matched workstream whose hook prints nothing is an error" || bad "hook-silent detection"
import sys; sys.path.insert(0, sys.argv[1]); import work
work.run_brief_hook_dry = lambda cwd: (None, 0.1, "boom")
result, _ = work.run_doctor(sys.argv[2])
hits = [f for f in result["findings"] if f["id"] == "D-brief.hook-silent"]
assert hits and hits[0]["severity"] == "error" and "boom" in hits[0]["cause"], result
work.run_brief_hook_dry = lambda cwd: ("brief", 9.0, None)
result, _ = work.run_doctor(sys.argv[2])
assert [f["severity"] for f in result["findings"] if f["id"] == "D-brief.slow"] == ["warn"], result
PY

echo "-- D-hooks"
CFG="$TMP/cfg"; mkdir -p "$CFG/plugins/cache/mkt/100x/0.1.0/hooks"
echo '{"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py\""}]}]}}' \
  > "$CFG/plugins/cache/mkt/100x/0.1.0/hooks/hooks.json"
HUNDREDX_CONFIG_DIRS="$TMP/absent:$CFG" doc
expect D-hooks.installed-old warn
field D-hooks.installed-old fix | grep -qF "CLAUDE_CONFIG_DIR=$CFG claude plugin uninstall 100x@mkt && CLAUDE_CONFIG_DIR=$CFG claude plugin marketplace update mkt && CLAUDE_CONFIG_DIR=$CFG claude plugin install 100x@mkt" \
  && ok "  fix: uninstall, marketplace update, install for that config dir" || bad "  reinstall fix: $(field D-hooks.installed-old fix)"
grep -qF "$TMP/absent" "$OUT/r.out" && bad "  an absent config dir was reported" || ok "  an absent config dir is skipped silently"
CLAUDE_CONFIG_DIR="$CFG" doc
expect D-hooks.installed-old warn
mkdir -p "$CFG/plugins/cache/mkt/100x/0.10.0/hooks"
cp "$ROOT/hooks/hooks.json" "$CFG/plugins/cache/mkt/100x/0.10.0/hooks/hooks.json"
HUNDREDX_CONFIG_DIRS="$CFG" doc
expect D-hooks.installed-old none
[ "$drc" -eq 0 ] && ok "  the newest installed version (0.10.0 > 0.1.0) registers them: exit 0" || bad "  newest version exit $drc"
mkdir -p "$TMP/cfg-empty"
HUNDREDX_CONFIG_DIRS="$TMP/cfg-empty" doc
expect D-hooks.not-installed info
python3 - "$ROOT/scripts" "$TMP" >"$OUT/r.out" 2>&1 <<'PY' && ok "this plugin's hooks.json without the work hooks is an error" || bad "plugin hooks detection"
import json, pathlib, sys; sys.path.insert(0, sys.argv[1]); import work
fake = pathlib.Path(sys.argv[2]) / "fake-plugin"; (fake / "hooks").mkdir(parents=True)
(fake / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"SessionStart": []}}))
work.PLUGIN_ROOT = fake
found = work.check_hooks({})
assert [f["severity"] for f in found if f["id"] == "D-hooks.plugin"] == ["error"], found
assert "work_brief.py" in found[0]["what"] and "work_fork_guard.py" in found[0]["what"], found
PY

echo "-- D-backup"
HUNDREDX_WORK_BACKUP_HINT= doc
expect D-backup.none warn
HUNDREDX_WORK_BACKUP_HINT="$TMP/gone.txt" doc
expect D-backup.hint-missing error
[ "$drc" -eq 1 ] && ok "  an error exits 1" || bad "  error exit $drc"
HUNDREDX_WORK_DIR="$TMP/none" doc
expect D-backup.not-named warn
field D-backup.not-named fix | grep -qF "add this line to $BK/mirrors.txt: $TMP/none" && ok "  fix names the exact line to add" || bad "  not-named fix"
mkdir -p "$HOME/.config/100x"
printf '{"backup_hint": "%s"}\n' "$BK/mirrors.txt" > "$HOME/.config/100x/work.json"
printf '.config/100x/work union\n' > "$TMP/home-hint.txt"
HUNDREDX_WORK_BACKUP_HINT= HUNDREDX_WORK_DIR="$HOME/.config/100x/work" doc
expect D-backup.none none; expect D-backup.not-named warn
HUNDREDX_WORK_BACKUP_HINT="$TMP/home-hint.txt" HUNDREDX_WORK_DIR="$HOME/.config/100x/work" doc
expect D-backup.not-named none
rm "$HOME/.config/100x/work.json"
echo "recent" >> "$BK/mirrors.txt"; gc commit -q -am recent
doc; expect D-backup.unpushed none
GIT_COMMITTER_DATE="2020-01-01T00:00:00Z" GIT_AUTHOR_DATE="2020-01-01T00:00:00Z" gc commit -q --allow-empty -m old
git -C "$BK" update-ref refs/remotes/origin/main HEAD~2
GIT_COMMITTER_DATE="2020-01-02T00:00:00Z" gc commit -q --allow-empty -m older-head
doc
expect D-backup.unpushed warn
field D-backup.unpushed what | grep -qF "3 commit(s) ahead of origin/main" && ok "  counts commits ahead from local refs" || bad "  ahead count: $(field D-backup.unpushed what)"
mkdir -p "$BK/.state"; printf 'rebase stopped: conflict in mirrors.txt\nsecond line\n' > "$BK/.state/remote-sync-failed"
doc
expect D-backup.sync-failed error
field D-backup.sync-failed what | grep -qF "rebase stopped: conflict in mirrors.txt" && ok "  shows the marker's first lines" || bad "  marker text"
mv "$BK/.state/remote-sync-failed" "$TMP/sync-marker"
git -C "$BK" branch -q --unset-upstream
doc; expect D-backup.no-upstream info; expect D-backup.unpushed none
git -C "$BK" update-ref refs/remotes/origin/main HEAD
git -C "$BK" branch -q --set-upstream-to=origin/main main
doc; expect D-backup.sync-failed none; expect D-backup.unpushed none; expect D-backup.no-upstream none

echo "-- D-holds"
HUNDREDX_WORK_DIR="$R2" doc
expect D-holds.stale info
field D-holds.stale fix | grep -qF "100x work release-hold 12 --ws old" && ok "  fix releases that hold" || bad "  stale fix"
expect D-holds.handoff info
doc; expect D-holds.stale none; expect D-holds.handoff none

echo "-- usage, text output, read-only"
"$W" work doctor --cwd "$TMP/does-not-exist" >"$OUT/r.out" 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "doctor --cwd <missing dir>: usage error, exit 2" || bad "missing --cwd exit $rc"
"$W" work doctor --bogus >"$OUT/r.out" 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "doctor --bogus: exit 2" || bad "bogus flag exit $rc"
HUNDREDX_WORK_DIR="$R2" "$W" work doctor >"$OUT/r.out" 2>&1; rc=$?
[ "$rc" -eq 1 ] && ok "text output on a broken record exits 1" || bad "text exit $rc"
has "WARN  D-record.mode:"; has "      cause: "; has "      fix:   chmod 700"; has "INFO  D-holds.stale:"
has "checks: D-record warn, D-events warn"
python3 - "$OUT/r.out" <<'PY' && ok "  findings are ordered error, warn, info" || bad "  severity order"
import re, sys; sev = re.findall(r"^(ERROR|WARN|INFO) ", open(sys.argv[1]).read(), re.M)
assert sev == sorted(sev, key=["ERROR", "WARN", "INFO"].index), sev
PY
mv "$TMP/sync-marker" "$BK/.state/remote-sync-failed"
# The suite itself commits to the backup repo, so the first comparison leaves out what the
# test changed there; the second, below, covers the backup repo whole across doctor runs.
mine() { grep -v -e "$BK/.git" -e "$BK/.state" -e "$BK/mirrors.txt"; }
diff <(printf '%s\n' "$SNAP_BEFORE" | mine) <(snapshot "$REC" "$R2" "$BK" "$REPO" | mine) >"$OUT/r.out" \
  && ok "doctor wrote nothing in the record dirs or the repo" || bad "doctor changed a file"
SNAP_BK="$(snapshot "$REC" "$R2" "$BK" "$REPO")"
doc; HUNDREDX_WORK_DIR="$R2" doc; "$W" work doctor >/dev/null 2>&1
[ "$(snapshot "$REC" "$R2" "$BK" "$REPO")" = "$SNAP_BK" ] \
  && ok "doctor wrote nothing in the backup repo either (incl. .git)" || bad "doctor changed the backup repo"
rm -f "$BK/.state/remote-sync-failed"
unset HUNDREDX_WORK_BACKUP_HINT
cd "$REPO" || exit 1

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
