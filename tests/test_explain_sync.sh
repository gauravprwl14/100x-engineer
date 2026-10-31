#!/usr/bin/env bash
# Regression suite for scripts/explain_sync.py: drift since the pin is reported per merge
# and per page, the pin refuses to move while a page fails flow check, a folder-level node
# ref is not a dependency, and a rewritten history is an error, not a silent re-sync.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
ES="$ROOT/scripts/explain_sync.py"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-60s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-60s\n' "$1"; [ -s "$TMP/out" ] && sed 's/^/       /' "$TMP/out" | head -12; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" "${2:-$TMP/out}" && ok "has: $1" || bad "missing: $1"; }
no()   { grep -qF -- "$1" "${2:-$TMP/out}" && bad "false positive: $1" || ok "absent: $1"; }
run()  { python3 "$ES" "$@" --repo "$R" > "$TMP/out" 2>&1; }

R="$TMP/repo"; mkdir -p "$R/src" "$R/other" "$R/explain/alpha"; cd "$R"
git init -q -b main; git config user.email e@e; git config user.name e
printf 'def greet():\n    return "hello"\n' > src/app.py
printf 'x = 1\n' > other/util.py
cat > explain/alpha/scenario.json <<'JSON'
{"schema": 1, "title": "Greeting", "subject": {"kind": "concept", "lede": "How the app greets."},
 "nodes": [{"id": "app", "role": "service", "label": "App", "ref": "other/"}],
 "evidence": {"g": {"at": "src/app.py:2", "anchor": "hello"}},
 "scenarios": [{"id": "s", "kind": "happy", "title": "Greet",
                "steps": [{"t": "The app says hello", "do": [["note", "hi"]], "ev": ["g"]}]}]}
JSON
git add -A; git commit -qm init

echo "== no pin yet =="
run status; rc_is 1 $? "status with no pin exits 1"
has "pin none"
run pin; rc_is 0 $? "pin on a clean page exits 0"
has "pinned none ->"
[ -f explain/.sync.json ] && ok "state file written" || bad "no explain/.sync.json"
git add -A; git commit -qm "pin docs"
run status; rc_is 0 $? "a docs-only commit after the pin: still in sync"
has "explain_sync: in sync"

echo "== a merge touching a folder the page names only as a box label =="
git switch -qc feat/other; echo 'y = 2' >> other/util.py; git commit -qam "util"
git switch -q main; git merge -q --no-ff feat/other -m "Merge feat/other"
run status; rc_is 1 $? "a merge since the pin exits 1"
has "Merge feat/other"
has "ok   alpha"
has "no page affected"
no "SYNC alpha"

echo "== a merge moving the page's cited line =="
git switch -qc feat/app
printf '# greeting module\n\n\ndef greet():\n    return "hello"\n' > src/app.py
git commit -qam "move greet"
git switch -q main; git merge -q --no-ff feat/app -m "Merge feat/app"
run status; rc_is 1 $? "drift exits 1"
has "SYNC alpha"
no "cites changed src/app.py"        # only lines were inserted above: the cited text is intact
has "flow check: 1 finding(s)"       # but it moved more than two lines, which check catches
has "Merge feat/app"
run pin; rc_is 2 $? "pin refuses while a page fails flow check"
has "alpha fail flow check"

echo "== re-cite, then pin =="
sed -i.bak 's#src/app.py:2#src/app.py:5#' explain/alpha/scenario.json && rm explain/alpha/scenario.json.bak
git commit -qam "resync alpha"
run pin; rc_is 0 $? "pin after the page checks clean"
git commit -qam "pin"
run status; rc_is 0 $? "in sync after the pin"

echo "== line-aware: an edit far from the cited line, then a rewrite of it =="
printf '\n\n\n\n\n\n\ndef bye():\n    return "bye"\n' >> src/app.py
git commit -qam "add bye"
run status; rc_is 1 $? "a merge since the pin exits 1"
has "ok   alpha"
no "SYNC alpha"
sed -i.bak 's/return "hello"/return "hello there"/' src/app.py && rm src/app.py.bak
git commit -qam "reword hello"
run status; rc_is 1 $? "rewriting the cited line exits 1"
has "SYNC alpha: cites changed src/app.py"
python3 "$ES" pin --repo "$R" --force > "$TMP/out" 2>&1; git commit -qam "pin"

echo "== rewritten history =="
python3 - "$R/explain/.sync.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d["pin"] = "0" * 40; json.dump(d, open(p, "w"))
PY
run status; rc_is 2 $? "unknown pin exits 2"
git checkout -q explain/.sync.json
side=$(git commit-tree "HEAD~3^{tree}" -p HEAD~3 -m side)   # a commit main never contains
python3 - "$R/explain/.sync.json" "$side" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d["pin"] = sys.argv[2]; json.dump(d, open(p, "w"))
PY
run status; rc_is 2 $? "pin not on main's history exits 2"
has "history was rewritten"

echo "explain_sync: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
