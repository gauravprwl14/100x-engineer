#!/usr/bin/env bash
# flow.py: the explain skill's scenario checker, reducer and build. Clean inputs must stay
# quiet (the example, the all-actions fixture, a fresh starter); each seeded bad case in
# tests/flow/bad/ must exit 1 with exactly one finding naming its defect; unreadable input
# exits 2. The golden states the JS player is tested against must match the reducer.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
F="$ROOT/scripts/flow.py"
FIX="$ROOT/tests/flow"
EX="$ROOT/skills/explain/assets/examples/stale-writeback.json"
BULK="$ROOT/skills/explain/assets/examples/bulk-import.json"
TMP="$(cd "$(mktemp -d)" && pwd -P)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-64s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "$1"; sed 's/^/       /' "$OUT/r.out" | head -12; }
run() {
  local exp="$1" label="$2"; shift 2
  python3 "$F" "$@" >"$OUT/r.out" 2>&1; local got=$?
  [ "$got" -eq "$exp" ] && ok "$label" || bad "$label (exit exp=$exp got=$got)"
}
has()   { grep -q -- "$1" "$OUT/r.out" && ok "  reports: $1" || bad "  NOT reported: $1"; }
hasnt() { grep -q -- "$1" "$OUT/r.out" && bad "  unexpectedly reports: $1" || ok "  does not report: $1"; }
count() { local n; n=$(grep -c "$1" "$OUT/r.out"); [ "$n" -eq "$2" ] && ok "  $2 x $1" || bad "  $n x $1, expected $2"; }

# the synthetic app the example cites, as a throwaway repo (no nested .git is committed)
export GIT_CONFIG_GLOBAL="$TMP/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --global user.email t@t; git config --global user.name t
REPO="$TMP/app"; cp -R "$FIX/fixture-app" "$REPO"
mkdir -p "$REPO/packages/@scope" && printf 'export const scoped = 1;\n' >"$REPO/packages/@scope/x.ts"
git -C "$REPO" init -q && git -C "$REPO" add -A && git -C "$REPO" commit -qm fixture
SHA="$(git -C "$REPO" rev-parse HEAD)"

echo "--- clean inputs stay quiet"
run 0 "example passes at its own tier (heavy)" check "$EX" --repo "$REPO"
has "0 finding(s)"
has "HAZARD race#4: stale-writeback cache cache key note:a <- store db key notes/a"
count "HAZARD" 1
hasnt "HAZARD happy"
hasnt "HAZARD fix-set-if-fresh"
run 0 "example passes with --json" check "$EX" --repo "$REPO" --json
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d["findings"]==[] and len(d["hazards"])==1 else 1)' "$OUT/r.out" \
  && ok "  --json: no findings, one hazard (the fix has none)" || bad "  --json shape"
run 0 "bulk-import example passes at heavy (queues, workers, compare, no evidence)" check "$BULK" --tier heavy
has "0 finding(s), 0 hazard(s)"
run 1 "bulk-import at --tier light is over budget" check "$BULK" --tier light
has "over budget (light): 12 nodes, max 8"
run 0 "all-actions fixture passes (reply status, ids like C3, a cited set-if-fresh)" check "$FIX/all-actions.json" --repo "$REPO"
run 0 "subject.sha pins unpinned evidence" check <(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["sha"]=sys.argv[2]; print(json.dumps(d))' "$EX" "$SHA") --repo "$REPO"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["evidence"]["e-ttl"]["at"]+="@"+sys.argv[2]; print(json.dumps(d))' "$EX" "$SHA" >"$TMP/pinned.json"
run 0 "an @sha on one evidence entry resolves" check "$TMP/pinned.json" --repo "$REPO"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["evidence"]["e-ttl"]={"at": "packages/@scope/x.ts:1@"+sys.argv[2], "anchor": "scoped = 1"}; print(json.dumps(d))' "$EX" "$SHA" >"$TMP/scoped.json"
run 0 "a path holding @ resolves: packages/@scope/x.ts:1@<sha>" check "$TMP/scoped.json" --repo "$REPO"
has "0 finding(s)"
run 0 "new writes a starter" new demo-flow --out "$TMP/new/demo-flow.json"
run 0 "the starter passes check as written" check "$TMP/new/demo-flow.json"
run 2 "new refuses to overwrite" new demo-flow --out "$TMP/new/demo-flow.json"
run 2 "new refuses a bad slug" new "Bad Slug"
run 2 "new refuses a path-traversal slug" new "../escape"
has "refusing name"
[ ! -e "$ROOT/escape.json" ] && ok "  nothing written outside" || bad "  escape.json written"

echo "--- seeded bad cases: exit 1, exactly one finding, the right message"
expect_bad() {  # <case> <message>
  run 1 "bad/$1" check "$FIX/bad/$1.json" --repo "$REPO"
  has "$2"; count "FINDING" 1
}
expect_bad bad-anchor           "bad anchor: 'cache.fetch(' not within ±2 lines of src/notes.js:7"
expect_bad absence-with-hits    "absence contradicted: says 0 hit(s)"
expect_bad bare-number          "bare number '3' in prose"
expect_bad over-budget-light    "over budget (light): 9 steps"
expect_bad expect-contradiction "expect contradicts reducer: hit expected \"hit\", reducer has \"miss\""
expect_bad issue-unfixed        "issue has neither fixed_by nor open: true"
expect_bad unknown-action       "unknown action 'cache.fetch' (did you mean"
expect_bad wrong-arity          "wrong arity: send takes 2-3 argument(s), got 1"
expect_bad dangling-node        "unknown node 'apii'"
expect_bad hazard-undeclared    "undeclared hazard: the reducer produces stale-writeback"
expect_bad set-if-fresh-no-ev   "cache.set-if-fresh is atomic only in the reducer: cite in ev the primitive"

echo "--- the same example under other conditions"
run 1 "example at --tier light is over budget" check "$EX" --repo "$REPO" --tier light
has "over budget (light): 3 scenarios, max 2"
has "NOTE compare is a heavy-tier field"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][1].pop("fixed_by"); d["scenarios"][1]["open"]=True; print(json.dumps(d))' "$EX" >"$TMP/open.json"
run 0 "an issue marked open: true needs no fix" check "$TMP/open.json" --repo "$REPO"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][1]["steps"][4].pop("hazard"); print(json.dumps(d))' "$EX" >"$TMP/nohz.json"
run 1 "dropping the declared hazard is caught" check "$TMP/nohz.json" --repo "$REPO"
has "scenario race step 4: undeclared hazard"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["kind"]="pr"; print(json.dumps(d))' "$EX" >"$TMP/pr.json"
run 1 "a pr subject without subject.sha is rejected" check "$TMP/pr.json" --repo "$REPO"
has "subject.kind pr needs subject.sha"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["evidence"]["e-ttl"]["at"]="src/notes.js:99"; print(json.dumps(d))' "$EX" >"$TMP/far.json"
run 1 "a line past the end of the file is a bad anchor" check "$TMP/far.json" --repo "$REPO"
has "bad anchor: src/notes.js has 19 lines"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][0]["steps"][4]["do"][0][3]="200 then 3 retries"; print(json.dumps(d))' "$EX" >"$TMP/reply.json"
run 1 "a reply label allows the status, not other digits" check "$TMP/reply.json" --repo "$REPO"
has "bare number '3'"; hasnt "bare number '200'"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["title"]["ja"]="遅い読み取り 2 回"; print(json.dumps(d))' "$EX" >"$TMP/ja.json"
run 1 "a bare number in the ja text is caught too" check "$TMP/ja.json" --repo "$REPO"
has "title.ja: bare number '2'"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["pr"]=1479; d["title"]["en"]="PR 1479: a slow read writes a stale note back"; d["scenarios"][0]["steps"][4]["t"]="Reply; a 5xx or a 4xx skips the fill"; print(json.dumps(d))' "$EX" >"$TMP/pr-num.json"
run 0 "the subject's own PR number and HTTP classes (5xx, 4xx) are not bare numbers" check "$TMP/pr-num.json" --repo "$REPO"
hasnt "bare number"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["pr"]=1479; d["title"]["en"]="PR 1480 is another PR"; print(json.dumps(d))' "$EX" >"$TMP/pr-other.json"
run 1 "another PR's number is still a bare number" check "$TMP/pr-other.json" --repo "$REPO"
has "title.en: bare number '1480'"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["pr"]=1479; d["scenarios"][0]["steps"][4]["t"]="Reply within 15 min"; print(json.dumps(d))' "$EX" >"$TMP/untagged.json"
run 1 "an untagged '15 min' still fails" check "$TMP/untagged.json" --repo "$REPO"
has "bare number '15'"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][0]["steps"][3]["t"]="TTL of {{ttl_typo}}"; print(json.dumps(d))' "$EX" >"$TMP/ph.json"
run 1 "a placeholder with no number is caught" check "$TMP/ph.json" --repo "$REPO"
has "unknown number '{{ttl_typo}}'"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][0]["steps"][0]["evv"]=[]; print(json.dumps(d))' "$EX" >"$TMP/key.json"
run 1 "an unknown key gets a did-you-mean" check "$TMP/key.json" --repo "$REPO"
has "unknown key 'evv' (did you mean 'ev'?)"

python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["evidence"]["e-ttl"].pop("anchor"); d["evidence"]["e-no-version-check"].pop("git_grep"); print(json.dumps(d))' "$EX" >"$TMP/malformed.json"
run 1 "malformed evidence is a finding, not a crash" check "$TMP/malformed.json" --repo "$REPO"
hasnt "Traceback"; has "missing required key 'anchor'"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]="a string"; print(json.dumps(d))' "$EX" >"$TMP/subj-str.json"
run 1 "a subject that is a string is a finding, not a crash" check "$TMP/subj-str.json" --repo "$REPO"
hasnt "Traceback"; has "subject: must be an object, got str"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["sha"]=12345678; print(json.dumps(d))' "$EX" >"$TMP/sha-int.json"
run 1 "a non-string subject.sha is a finding, not a crash" check "$TMP/sha-int.json" --repo "$REPO"
hasnt "Traceback"; has "subject.sha: must be a hex commit SHA"; count "FINDING" 1
# every value of the example swapped for a wrong type: check, build and reduce report, never raise
python3 - "$ROOT" "$EX" "$REPO" "$TMP" >"$OUT/r.out" 2>&1 <<'PY3'
import contextlib, copy, io, json, sys
root, ex, repo, tmp = sys.argv[1:]
sys.path.insert(0, root + "/scripts"); import flow
base = json.load(open(ex))
def paths(v, p=()):
    yield p
    for k, x in (v.items() if isinstance(v, dict) else enumerate(v) if isinstance(v, list) else ()):
        yield from paths(x, p + (k,))
crashes, runs = [], 0
for p in list(paths(base))[1:]:
    for wrong in ("s", 7, [[1]], {"x": 1}):
        d = copy.deepcopy(base); t = d
        for k in p[:-1]: t = t[k]
        t[p[-1]] = wrong
        open(tmp + "/wrong.json", "w").write(json.dumps(d))
        for argv in (["check", tmp + "/wrong.json", "--repo", repo], ["build", tmp + "/wrong.json", "--out", tmp + "/wrong-site"], ["reduce", tmp + "/wrong.json"]):
            runs += 1
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    flow.main(argv)
            except Exception as e:
                crashes.append(f"{argv[0]} {p} = {wrong!r}: {type(e).__name__}: {e}")
print(f"{runs} runs, {len(crashes)} crash(es)"); print("\n".join(crashes[:5]))
sys.exit(1 if crashes else 0)
PY3
[ $? -eq 0 ] && ok "  every wrong-typed value is reported, never a traceback ($(head -1 "$OUT/r.out"))" || bad "  a wrong-typed value crashes flow.py"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][2]["branch"]["at"]=99; print(json.dumps(d))' "$EX" >"$TMP/far-branch.json"
run 1 "branch.at past the source's steps is a finding" check "$TMP/far-branch.json" --repo "$REPO"
has "branch.at 99 is past the 7 step(s) of race"
echo "--- cache.set-if-fresh: writes when fresh, skips without a hazard when a write landed"
run 0 "reduce marks the skipped fill" reduce "$EX" --scenario fix-set-if-fresh
has "#4 active=cache hit=None caches={\"cache\": {}}"; has "SKIPPED cache.note:a."; hasnt "HAZARD"
python3 "$F" reduce "$EX" --scenario fix-set-if-fresh --json >"$OUT/sif.json" 2>&1
python3 - "$OUT/sif.json" >"$OUT/r.out" 2>&1 <<'PY2'
import json, sys
s = json.load(open(sys.argv[1]))["scenarios"]["fix-set-if-fresh"]
skip, fresh = s[4], s[6]
assert skip["skipped"] == [{"cache": "cache", "key": "note:a", "store": "db", "store_key": "notes/a", "read": "v1", "current": "v2"}], skip["skipped"]
assert "note:a" not in skip["caches"]["cache"] and skip["hazards"] == []
assert fresh["caches"]["cache"]["note:a"] == {"v": "v2", "stale": False, "src": ["db", "notes/a"]} and fresh["skipped"] == []
print("set-if-fresh ok")
PY2
[ $? -eq 0 ] && ok "  changed source: skipped, cache empty, no hazard; fresh source: written" || bad "  set-if-fresh states"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][2]["steps"][0]["do"][0][3]="v1"; print(json.dumps(d))' "$EX" >"$TMP/sif-lit.json"
run 1 "set-if-fresh with a literal value is a finding" check "$TMP/sif-lit.json" --repo "$REPO"
has "cache.set-if-fresh needs a \$variable bound by db.read"; count "FINDING" 1
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][2]["steps"][0]["do"][0][3]="$nope"; print(json.dumps(d))' "$EX" >"$TMP/sif-unbound.json"
run 1 "set-if-fresh with an unbound variable is a reducer finding" check "$TMP/sif-unbound.json" --repo "$REPO"
has "cache.set-if-fresh: variable '\$nope' is unbound"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][2]["steps"][0]["hazard"]="stale-writeback"; print(json.dumps(d))' "$EX" >"$TMP/sif-hz.json"
run 1 "declaring a hazard on a guarded fill is a contradiction" check "$TMP/sif-hz.json" --repo "$REPO"
has "hazard stale-writeback is declared but not produced"

echo "--- unreadable input exits 2"
printf '{ not json' >"$TMP/broken.json"
run 2 "invalid JSON" check "$TMP/broken.json"
has "cannot read"
run 2 "missing file" check "$TMP/nope.json"
printf '{"schema": 2}' >"$TMP/s2.json"
run 2 "schema other than 1" check "$TMP/s2.json"
mkdir -p "$TMP/nogit"
( cd "$TMP/nogit" && python3 "$F" check "$EX" ) >"$OUT/r.out" 2>&1
[ $? -eq 2 ] && ok "evidence outside a git repo exits 2" || bad "evidence outside a git repo"
has "not a git repository"

echo "--- reducer and golden states"
run 0 "reduce prints every step" reduce "$EX" --scenario race
count "^  #" 7
has "#4 active=cache"
run 2 "reduce with an unknown scenario exits 2" reduce "$EX" --scenario nope
run 1 "reduce refuses a structurally bad file" reduce "$FIX/bad/unknown-action.json"
# tests/flow/states.json = {"schema":1, "cases":[{"file", "scenarios"}]}, each case the
# `reduce <file> --json` output; regenerate with the same python block after a reducer change.
python3 - "$ROOT" "$FIX/states.json" >"$OUT/r.out" 2>&1 <<'PY'
import json, pathlib, subprocess, sys
root, golden = pathlib.Path(sys.argv[1]), json.load(open(sys.argv[2]))
bad = 0
for case in golden["cases"]:
    out = subprocess.run([sys.executable, str(root / "scripts/flow.py"), "reduce",
                          str(root / case["file"]), "--json"], capture_output=True, text=True)
    now = json.loads(out.stdout)["scenarios"]
    if now != case["scenarios"]:
        bad = 1; print(f"golden drift: {case['file']}")
print("cases:", ", ".join(c["file"] for c in golden["cases"]))
sys.exit(bad)
PY
[ $? -eq 0 ] && ok "states.json matches the reducer for every case" || bad "states.json drifted from the reducer"
has "stale-writeback.json"; has "all-actions.json"; has "bulk-import.json"
if command -v node >/dev/null 2>&1; then
  node --test "$FIX/reduce.test.mjs" >"$OUT/r.out" 2>&1
  [ $? -eq 0 ] && ok "JS player reducer equals flow.py on every golden case (node --test)" || bad "JS reducer drifted from flow.py"
  has "fail 0"
else
  echo "  SKIP JS reducer parity: node not installed"
fi

echo "--- build"
run 2 "build without engine assets exits 2" build "$EX" --out "$TMP/site" --assets "$TMP/no-assets"
has "engine assets not found"
mkdir -p "$TMP/assets"
printf '<title>{{flow_title}}</title><style>{{flow_css}}</style><script>{{flow_js}}</script><script type="application/json" id="flow-data">{{flow_data}}</script><p>{{flow_tier}}</p>' >"$TMP/assets/shell.html"
printf 'var s = "</script>";' >"$TMP/assets/flow-player.js"
printf 'body{}' >"$TMP/assets/flow-player.css"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["lede"]["en"]+=" </script><!--"; print(json.dumps(d))' "$EX" >"$TMP/esc.json"
run 0 "build inlines the assets" build "$TMP/esc.json" --out "$TMP/site" --assets "$TMP/assets"
python3 - "$TMP/site/index.html" >"$OUT/r.out" 2>&1 <<'PY'
import json, re, sys
page = open(sys.argv[1]).read()
data = re.search(r'<script type="application/json" id="flow-data">(.*?)</script>', page, re.S).group(1)
assert "</" not in data and "<!--" not in data, "unescaped < in data"
d = json.loads(data)
assert d["tier"] == "heavy" and d["scenario"]["subject"]["lede"]["en"].endswith("</script><!--")
assert '"<\\/script>"' in page, "</script in JS not escaped"
assert "{{flow_" not in page and "<p>heavy</p>" in page
print("build ok")
PY
[ $? -eq 0 ] && ok "  data round-trips with every < escaped; JS </script escaped" || bad "  build escaping"
printf '<html></html>' >"$TMP/assets/shell.html"
run 2 "a shell without the tokens exits 2" build "$EX" --out "$TMP/site2" --assets "$TMP/assets"
has "shell.html lacks"
run 1 "build refuses a structurally bad scenario" build "$FIX/bad/wrong-arity.json" --out "$TMP/site3" --assets "$TMP/assets"

echo "--- build refuses what check rejects at the same tier"
run 1 "build --tier light refuses the example check --tier light rejects" build "$EX" --tier light --out "$TMP/refused"
has "over budget (light): 3 scenarios, max 2"; has "flow build: refused"
[ ! -e "$TMP/refused/index.html" ] && ok "  no page written" || bad "  a refused build wrote index.html"
python3 "$F" check "$EX" --tier light --repo "$REPO" | grep FINDING | sort >"$TMP/check.f"
python3 "$F" build "$EX" --tier light --repo "$REPO" --out "$TMP/refused" 2>&1 | grep FINDING | sort >"$TMP/build.f"
[ -s "$TMP/check.f" ] && cmp -s "$TMP/check.f" "$TMP/build.f" && ok "  build reports the same findings as check" || bad "  build and check findings differ"
run 1 "build refuses a bare number in prose" build "$TMP/ja.json" --out "$TMP/refused"
has "title.ja: bare number '2'"
run 0 "build skips evidence without --repo" build "$TMP/far.json" --out "$TMP/far-site"
run 1 "build --repo checks evidence too" build "$TMP/far.json" --repo "$REPO" --out "$TMP/far-site"
has "bad anchor: src/notes.js has 19 lines"

echo "--- build with the real engine: tier in the data, the .md export"
# the example within the light budget: the happy path dropped, compare is heavy-only
LIGHT="$TMP/stale-writeback-light.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"]=d["scenarios"][1:]; d.pop("compare", None); print(json.dumps(d))' "$EX" >"$LIGHT"
run 0 "build --tier light writes index.html and explain.md" build "$LIGHT" --tier light --out "$TMP/real-light"
has "(tier light)"
python3 - "$TMP/real-light" >"$OUT/r.out" 2>&1 <<'PY2'
import json, pathlib, re, sys
d = pathlib.Path(sys.argv[1])
page = (d / "index.html").read_text()
data = json.loads(re.search(r'<script type="application/json" id="flow-data">(.*?)</script>', page, re.S).group(1))
assert data["tier"] == "light" and 'data-tier="light"' in page and "{{flow_" not in page
md = (d / "explain.md").read_text()
assert md.startswith("# Notes service: a slow read writes a stale note back into the cache\n"), md[:80]
for want in ("## A PATCH lands between", "| # | what happens | state after | evidence |",
             "**HAZARD stale-writeback**", "fill skipped: db[notes/a] changed", "Steps 1–4 are the same as `race`",
             "## Decision", "(chosen)", "| `cache_ttl` | 300 s | verified | `src/notes.js:2` |", "the TTL of 300 s runs out"):
    assert want in md, want
assert "{{" not in md, "unfilled placeholder in explain.md"
print("md ok")
PY2
[ $? -eq 0 ] && ok "  page carries tier light; explain.md has tables, hazard, skip, decision, filled numbers" || bad "  light build / md export"
run 0 "build --tier heavy overrides nothing else" build "$BULK" --tier heavy --out "$TMP/real-heavy"
grep -q 'data-tier="heavy"' "$TMP/real-heavy/index.html" && ok "  heavy page carries tier heavy" || bad "  heavy tier missing"
grep -q '^## Plan B under load' "$TMP/real-heavy/explain.md" && ok "  bulk-import explain.md has every scenario" || bad "  bulk md"

echo "--- optional: the engine renders in headless Chrome (never required)"
CHROME="${FLOW_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
# <page> <width> [#hash]: the JSON tests/flow/smoke-probe.js leaves on <html data-probe>
probe() {
  python3 -c 'import sys; p=open(sys.argv[1]).read(); open(sys.argv[2], "w").write(p.replace("</body>", "<script>" + open(sys.argv[3]).read() + "</script></body>"))' "$1" "$1.probe.html" "$FIX/smoke-probe.js"
  "$CHROME" --headless=new --disable-gpu --no-first-run --window-size="$2",900 --virtual-time-budget=5000 --dump-dom "file://$1.probe.html${3:-}" 2>/dev/null \
    | python3 -c 'import html, re, sys; m = re.search(r"data-probe=\"([^\"]*)\"", sys.stdin.read()); print(html.unescape(m.group(1)) if m else "{}")'
}
if [ -x "$CHROME" ]; then
  # the light example is the light-budget variant; bulk-import is over the light budget
  for pair in "$LIGHT:light" "$EX:heavy" "$BULK:heavy"; do
    ex="${pair%:*}"; tier="${pair##*:}"; name="$(basename "$ex" .json) $tier"
    want=$(python3 "$F" reduce "$ex" --json | python3 -c 'import json,sys; print(",".join(f"{k}:{len(v)}" for k,v in json.load(sys.stdin)["scenarios"].items()))')
    site="$TMP/smoke-$(basename "$ex" .json)-$tier"
    python3 "$F" build "$ex" --tier "$tier" --out "$site" >/dev/null 2>&1
    "$CHROME" --headless=new --disable-gpu --no-first-run --virtual-time-budget=5000 --dump-dom "file://$site/index.html" >"$OUT/r.out" 2>/dev/null
    tagline=$(grep -o '<html[^>]*>' "$OUT/r.out" | head -1)
    case "$tagline" in
      *data-flow-error*) bad "smoke $name: data-flow-error set" ;;
      *'data-flow-ok="true"'*"data-flow-steps=\"$want\""*|*"data-flow-steps=\"$want\""*'data-flow-ok="true"'*) ok "smoke $name: rendered, steps $want" ;;
      *) bad "smoke $name: no data-flow-ok with steps $want ($tagline)" ;;
    esac
    for w in 1280 400; do
      probe "$site/index.html" "$w" >"$OUT/r.out"
      python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("crossings")); sys.exit(0 if d.get("ok") == "true" and d.get("crossings") == [] else 1)' "$OUT/r.out" >>"$OUT/r.out" 2>&1 \
        && ok "  smoke $name at ${w}px: no map edge passes through a box it does not connect" || bad "  smoke $name at ${w}px: an edge crosses a box"
    done
  done
  # a deep link shows its card: present, not hidden, its top inside the viewport; an inherited
  # step's card is folded until the link opens it. Chrome's --screenshot paints a scrolled
  # viewport blank, so this reads the DOM, not a picture.
  for hash in race.4 fix-set-if-fresh.1; do
    probe "$TMP/smoke-stale-writeback-light-light/index.html" 1280 "#$hash" >"$OUT/r.out"
    python3 -c 'import json,sys; t=json.load(open(sys.argv[1])).get("target") or {}; sys.exit(0 if t and not t["hidden"] and 0 <= t["top"] < t["vh"] and t["h"] > 0 else 1)' "$OUT/r.out" \
      && ok "  smoke light #$hash: the card is present, shown and in the viewport" || bad "  smoke light #$hash: card missing, hidden or off screen"
  done
  probe "$TMP/smoke-stale-writeback-light-light/index.html" 1280 "#%E0%A4%A" >"$OUT/r.out"
  grep -q '"ok": *"true"' "$OUT/r.out" && ok "  smoke light: a malformed %-escape in the hash still renders" || bad "  smoke light: a malformed hash breaks the page"
else
  echo "  SKIP headless smoke: Google Chrome not found (set FLOW_CHROME to a Chrome binary)"
fi

echo
echo "flow: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
