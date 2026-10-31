#!/usr/bin/env bash
# Regression suite for scripts/code_ref.py and the `reference` key of an explain scenario
# (scripts/flow.py): the inventory comes from the parse tree, a stale reference is caught,
# a symbol or note naming code that is not there is a finding, and the build renders it.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
CR="$ROOT/scripts/code_ref.py"; FLOW="$ROOT/scripts/flow.py"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-60s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-60s\n' "$1"; [ -s "$TMP/out" ] && sed 's/^/       /' "$TMP/out" | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" "${2:-$TMP/out}" && ok "has: $1" || bad "missing: $1"; }
no()   { grep -qF -- "$1" "${2:-$TMP/out}" && bad "false positive: $1" || ok "absent: $1"; }

R="$TMP/repo"; mkdir -p "$R/pkg"; cd "$R"
git init -q; git config user.email e@e; git config user.name e
cat > pkg/mod.py <<'PY'
"""A module that registers checks."""
CHECKS = []


def register(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@register("A")
def check_a(x):
    """Say whether x is big."""
    if x > 3 and x < 9:
        return True
    return False


def run(xs):
    return [check_a(x) for x in xs]


class Box:
    """Holds one value."""
    def get(self):
        return run([1])
PY
echo "hello" > notes.txt
git add -A; git commit -qm init

echo "== code_ref build =="
python3 "$CR" build pkg/mod.py > "$TMP/ref.json"; rc_is 0 $? "build exits 0"
python3 - "$TMP/ref.json" > "$TMP/out" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
f = d["files"][0]
by = {s["name"]: s for s in f["symbols"]}
print("doc:", f["doc"])
print("names:", sorted(by))
print("check_a.doc:", by["check_a"]["doc"])
print("check_a.decorators:", by["check_a"]["decorators"])
print("check_a.used_by:", by["check_a"]["used_by"])
print("check_a.branches:", by["check_a"]["branches"])
print("register.used_by:", by["register"]["used_by"])
print("Box.get.kind:", by["Box.get"]["kind"])
print("run.doc:", by["run"]["doc"])
PY
has "doc: A module that registers checks."
has "names: ['Box', 'Box.get', 'check_a', 'register', 'run']"
has "check_a.doc: Say whether x is big."
has "check_a.decorators: [\"register('A')\"]"
has "check_a.used_by: ['run']"
has "check_a.branches: 2"
has "register.used_by: []"            # a decorator line is not a use by the decorated function
has "Box.get.kind: method"
has "run.doc: None"

python3 "$CR" build pkg/mod.py --md > "$TMP/out"
has "| \`check_a\` \`@register('A')\` | 13–17 | Say whether x is big. | \`run\` | 2 |"
has "*no docstring*"

python3 "$CR" build notes.txt > "$TMP/out" 2>&1; rc_is 2 $? "non-Python file exits 2"
has "only Python (.py) files"

echo "== code_ref check: freshness =="
python3 "$CR" check "$TMP/ref.json" > "$TMP/out"; rc_is 0 $? "unchanged file is fresh"
echo "# edit" >> pkg/mod.py
python3 "$CR" check "$TMP/ref.json" > "$TMP/out"; rc_is 1 $? "edited file is stale"
has "stale: pkg/mod.py: changed since the reference was built"
git checkout -q pkg/mod.py

echo "== flow: reference key =="
cat > "$TMP/s.json" <<'JSON'
{"schema": 1, "title": "Checks", "subject": {"kind": "concept", "repo": "me/100x-tools",
 "lede": "How the 100x checks register and run."},
 "nodes": [{"id": "a", "role": "service", "label": "A"}],
 "scenarios": [{"id": "s", "kind": "happy", "title": "Run", "steps": [{"t": "Runs", "do": [["note", "x"]], "tag": "inferred"}]}],
 "reference": [{"path": "pkg/mod.py", "symbols": ["run", "check_a"], "notes": {"run": "Runs every check on each value."}}]}
JSON
python3 "$FLOW" check "$TMP/s.json" --repo "$R" > "$TMP/out"; rc_is 0 $? "valid reference checks clean"
no "bare number '100x'"                # a word of the subject's repo name is not a bare number

python3 - "$TMP/s.json" "$TMP/bad.json" "$TMP/shape.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
d["reference"][0]["symbols"].append("check_b")
d["reference"].append({"path": "pkg/missing.py"})
json.dump(d, open(sys.argv[2], "w"))
d["reference"][0]["notes"]["chek_a"] = "typo"
d["reference"].append({"path": "notes.txt"})
json.dump(d, open(sys.argv[3], "w"))
PY
# Against the code: only on a file with no shape errors, as evidence is.
python3 "$FLOW" check "$TMP/bad.json" --repo "$R" > "$TMP/out"; rc_is 1 $? "symbol or file not in the code fails"
has "no symbol 'check_b' in pkg/mod.py (did you mean 'check_a'?)"
has "reference[1].path: pkg/missing.py: not readable at"
python3 "$FLOW" check "$TMP/shape.json" > "$TMP/out"; rc_is 1 $? "bad reference shape fails without a repo"
has "notes.chek_a: has a note but is not in symbols"
has "reference[2].path: must be a repo-relative .py path"

echo "== flow build: renders the inventory =="
python3 "$FLOW" build "$TMP/s.json" --out "$TMP/page" --repo "$R" > "$TMP/out" 2>&1; rc_is 0 $? "build exits 0"
has "## Code reference" "$TMP/page/explain.md"
has "| \`run\` | 20–21 | Runs every check on each value. | \`Box.get\` | 1 |" "$TMP/page/explain.md"
has '"reference": [{"path": "pkg/mod.py"' "$TMP/page/index.html"
python3 "$FLOW" build "$TMP/s.json" --out "$TMP/page2" > "$TMP/out" 2>&1; rc_is 0 $? "build without --repo still succeeds"
has "no --repo given, so the page has no code reference"
no "## Code reference" "$TMP/page2/explain.md"

echo "code_ref: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
