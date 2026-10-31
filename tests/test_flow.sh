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
# a cited line that holds </script and <!--: the snippet must not close the page's data block
mkdir -p "$REPO/web" && printf 'const a = 1;\nconst page = "</script><!--";\n' >"$REPO/web/page.js"
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
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d["context"]["in_scope"] and len(d["terms"])==1 and d["outline"][0]["lines"][0]["tag"]=="inferred" else 1)' "$TMP/new/demo-flow.json" \
  && ok "  the starter carries a context, one term and an outline line tagged inferred" || bad "  starter lacks context/terms/outline"
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
expect_bad pr-without-context   "subject.kind pr needs context: say what the PR does for a user"
expect_bad issue-without-origin "scenario race.origin: issue has no origin"
expect_bad whatif-fix-uncited   "fix for what-if issue 'race' cites no evidence"
expect_bad jargon-title         "jargon in step title: 'getNote': add it to terms or say it in plain words"
expect_bad outline-line-uncited "outline line has no evidence: cite an ev id or tag it inferred"
expect_bad outline-step-out-of-range "step 3 is past the end of scenario happy (1 visible step(s), 0-based)"
expect_bad duplicate-term       "duplicate term 'ttl' (also terms\[0\])"
expect_bad diagram-kind-mismatch "diagram 'read': kind 'flowchart' does not match the source: check_diagrams reads a sequence diagram"
expect_bad diagram-uncited      "diagram 'read': diagram has no evidence: cite ev ids or tag it inferred"
expect_bad diagram-bad-mermaid  "diagram 'read': participant 'A' used before a \`participant\`/\`actor\` declaration"
expect_bad tldr-too-long        "tldr.how: keep it to one sentence: 219 characters, max 200"
expect_bad tldr-jargon          "tldr.how: jargon in tldr: 'getNote': add it to terms or say it in plain words"
expect_bad mindmap-two-roots    "diagram 'parts': mindmap has more than one root: 'Storage' is not indented deeper than the root 'root((Notes))'"

echo "--- context, terms, outline, origin, step code: what passes and what does not"
# mut <name> <python statement on d>: the example with one change, written to $TMP/<name>.json
mut() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); exec(sys.argv[2]); print(json.dumps(d))' "$EX" "$2" >"$TMP/$1.json"; }
mut plain-titles 'd["scenarios"][1]["steps"][2]["t"]="The PATCH passes the ACL check in hontai, e.g. as an admin"; d["scenarios"][1]["steps"][2]["t"]={"en": d["scenarios"][1]["steps"][2]["t"], "ja": "PATCH が ACL を通る"}'
run 0 "plain titles with ACL, PATCH, hontai and e.g. pass" check "$TMP/plain-titles.json" --repo "$REPO"
hasnt "jargon"
mut term-ok 'd["scenarios"][1]["steps"][2]["t"]="patchNote writes the new note"; d["terms"].append({"term": "patchNote", "means": "The function that saves a note."})'
run 0 "an identifier listed in terms passes (case-insensitive)" check "$TMP/term-ok.json" --repo "$REPO"
hasnt "jargon"
mut term-missing 'd["scenarios"][1]["steps"][2]["t"]="patchNote writes the new note"'
run 1 "the same title without the term is jargon" check "$TMP/term-missing.json" --repo "$REPO"
has "scenario race step 2.t: jargon in step title: 'patchNote'"; count "FINDING" 1
mut label-ok 'd["nodes"][2]["label"]="notesApi"; d["scenarios"][1]["steps"][2]["t"]="notesApi writes the new note"'
run 0 "a word that is a node label passes" check "$TMP/label-ok.json" --repo "$REPO"
hasnt "jargon"
mut id-ok 'd["nodes"][2]["id"]="notes_api"; d=json.loads(json.dumps(d).replace("\"api\"", "\"notes_api\"")); d["scenarios"][1]["steps"][2]["t"]="notes_api writes the new note"'
run 0 "a word that is a node id passes" check "$TMP/id-ok.json" --repo "$REPO"
hasnt "jargon"
mut jargon-kinds 'd["scenarios"][1]["steps"][2]["t"]="NoteStore runs Promise.all over cache_key"; d["scenarios"][1]["steps"][3]["t"]={"en": "Delete the key", "ja": "cacheKey を消す"}'
run 1 "PascalCase, dotted and snake_case words are jargon, in ja too" check "$TMP/jargon-kinds.json" --repo "$REPO"
has "'NoteStore'"; has "'Promise.all'"; has "'cache_key'"; has "step 3.t.ja: jargon in step title: 'cacheKey'"; count "FINDING" 4
mut tldr-gone 'd.pop("tldr")'
run 0 "tldr is optional" check "$TMP/tldr-gone.json" --repo "$REPO"
mut tldr-num 'd["tldr"]["how"]["en"] = "A read fills the cache 3 times."'
run 1 "a bare number in tldr is caught" check "$TMP/tldr-num.json" --repo "$REPO"
has "tldr.how.en: bare number '3' in prose"; count "FINDING" 1
mut tldr-ja-long 'd["tldr"]["what"]["ja"] = "長" * 201'
run 1 "tldr length is checked per language" check "$TMP/tldr-ja-long.json" --repo "$REPO"
has "tldr.what.ja: keep it to one sentence: 201 characters, max 200"; count "FINDING" 1
mut tldr-edge 'd["tldr"]["what"]["ja"] = "長" * 200'
run 0 "a tldr line of exactly 200 characters passes" check "$TMP/tldr-edge.json" --repo "$REPO"
mut tldr-term 'd["tldr"]["how"] = "patchNote writes the database, then notes-api clears the cache entry."; d["terms"].append({"term": "patchNote", "means": "The function that saves a note."})'
run 0 "an identifier listed in terms passes in tldr" check "$TMP/tldr-term.json" --repo "$REPO"
hasnt "jargon"
mut tldr-jargon-ja 'd["tldr"]["watch_out"]["ja"] = "cache_key が古いまま残る"'
run 1 "jargon in a tldr ja line is caught" check "$TMP/tldr-jargon-ja.json" --repo "$REPO"
has "tldr.watch_out.ja: jargon in tldr: 'cache_key'"; count "FINDING" 1
mut tldr-shape 'd["tldr"] = {"what": 7, "watchout": "x"}'
run 1 "tldr shape: required how, text values, unknown keys" check "$TMP/tldr-shape.json" --repo "$REPO"
has "tldr: missing required key 'how'"; has "tldr: unknown key 'watchout' (did you mean 'watch_out'?)"
mut tldr-shape-text 'd["tldr"]["what"] = 7'
run 1 "a tldr line that is not text is a finding" check "$TMP/tldr-shape-text.json" --repo "$REPO"
has "tldr.what: must be text"; count "FINDING" 1
mut jargon-in-d 'd["scenarios"][1]["steps"][2]["d"]="patchNote runs here"'
run 0 "jargon is checked in titles only, not in d" check "$TMP/jargon-in-d.json" --repo "$REPO"
mut code-digits 'd["scenarios"][1]["steps"][2]["code"]=["if retries > 3: wait(250)"]; d["outline"][0]["lines"][0]["code"]="retry 3 times"'
run 0 "digits in step code and outline code are not bare numbers" check "$TMP/code-digits.json" --repo "$REPO"
hasnt "bare number"
mut ctx-digits 'd["context"]["in_scope"].append("Up to 3 notes")'
run 1 "a bare number in context prose is caught" check "$TMP/ctx-digits.json" --repo "$REPO"
has "context.in_scope\[2\]: bare number '3'"
mut code-shape 'd["scenarios"][1]["steps"][2]["code"]="one string"'
run 1 "step code that is not a list of lines is a finding" check "$TMP/code-shape.json" --repo "$REPO"
has "step 2.code: must be a list of 1-8 pseudocode lines"
mut code-long 'd["scenarios"][1]["steps"][2]["code"]=["x"]*9'
run 1 "more than eight lines of step code is a finding" check "$TMP/code-long.json" --repo "$REPO"
has "must be a list of 1-8 pseudocode lines"
mut origin-bad 'd["scenarios"][1]["origin"]="imagined"'
run 1 "an origin outside the three values is a finding" check "$TMP/origin-bad.json" --repo "$REPO"
has "origin: must be one of in-code, what-if, found-in-review"
mut whatif-cited 'd["scenarios"][1]["origin"]="what-if"'
run 0 "a what-if issue whose fix cites evidence passes" check "$TMP/whatif-cited.json" --repo "$REPO"
mut ep-bad 'd["context"]["entry_points"][0]["scenario"]="nope"; d["context"]["entry_points"][1]["ev"]="e-nope"; d["context"]["entry_points"][1]["kind"]="url"'
run 1 "an entry point's scenario, ev and kind must resolve" check "$TMP/ep-bad.json" --repo "$REPO"
has "entry_points\[0\].scenario: unknown scenario"; has "entry_points\[1\].ev: unknown evidence id"; has "entry_points\[1\].kind: must be one of route"; count "FINDING" 3
mut scope-empty 'd["context"]["in_scope"]=[]; d["context"].pop("purpose")'
run 1 "context needs a purpose and one to eight in_scope items" check "$TMP/scope-empty.json" --repo "$REPO"
has "context: missing required key 'purpose'"; has "context.in_scope: must be a list of 1-8 text items"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["kind"]="pr"; d["subject"]["sha"]=sys.argv[2]; print(json.dumps(d))' "$EX" "$SHA" >"$TMP/pr-ctx.json"
run 0 "a pr subject with context and a pinned sha passes" check "$TMP/pr-ctx.json" --repo "$REPO"
mut terms-many 'd["terms"]=[{"term": "t%s" % chr(97+i), "means": "x"} for i in range(13)]'
run 1 "more than twelve terms is a finding" check "$TMP/terms-many.json" --repo "$REPO"
has "terms: must be a list of at most 12 terms"
mut outline-bad 'd["outline"][0]["scenario"]="nope"; d["outline"][1]["lines"][0]["ev"]="e-nope"; d["outline"][1]["lines"][1]["indent"]=7'
run 1 "an outline's scenario, line ev and indent must resolve" check "$TMP/outline-bad.json" --repo "$REPO"
has "outline\[0\].scenario: unknown scenario"; has "outline\[1\].lines\[0\].ev: unknown evidence id"; has "outline\[1\].lines\[1\].indent: must be an integer from 0 to 6"
mut outline-heavy 'd["outline"]=d["outline"]*2'
run 1 "four outlines are over the heavy budget" check "$TMP/outline-heavy.json" --repo "$REPO"
has "over budget (heavy): 4 outlines, max 3"
mut outline-inherited 'd["outline"][0]["scenario"]="fix-set-if-fresh"; d["outline"][0]["lines"][0]["steps"]=[6]'
run 0 "outline step indexes count inherited steps" check "$TMP/outline-inherited.json" --repo "$REPO"

echo "--- diagrams: mermaid through check_diagrams, kind, evidence, prose, budgets"
DG='d["diagrams"][0]'
mut dg-flow "$DG"'.update(kind="flowchart", source="flowchart LR\n  reader[\"Reader\"] --> api[\"notes-api\"]\n  api --> hit{\"cached?\"}\n  hit -->|\"yes\"| reader\n  hit -->|\"no\"| db[\"Database\"]")'
run 0 "a valid flowchart passes" check "$TMP/dg-flow.json" --repo "$REPO"
has "0 finding(s)"
mut dg-state "$DG"'.update(kind="state", source="stateDiagram-v2\n  [*] --> fresh\n  fresh --> stale: PATCH lands mid-read\n  stale --> [*]: TTL ends")'
run 0 "a valid state diagram passes" check "$TMP/dg-state.json" --repo "$REPO"
has "0 finding(s)"
mut dg-er "$DG"'.update(kind="er", source="erDiagram\n  NOTE ||--o{ REVISION : has")'
run 0 "a valid ER diagram passes" check "$TMP/dg-er.json" --repo "$REPO"
mut dg-class "$DG"'.update(kind="class", source="classDiagram\n  class NoteStore\n  NoteStore --> Cache")'
run 0 "a valid class diagram passes" check "$TMP/dg-class.json" --repo "$REPO"
run 0 "the example's mindmap passes as written" check "$EX" --repo "$REPO"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if [g["kind"] for g in d["diagrams"]] == ["sequence", "mindmap"] else 1)' "$EX" \
  && ok "  the example carries a sequence and a mindmap" || bad "  example diagram kinds"
MM='d["diagrams"][1]'
mut dg-mm-kind "$MM"'["kind"] = "sequence"'
run 1 "a mindmap source declared as another kind is a finding" check "$TMP/dg-mm-kind.json" --repo "$REPO"
has "diagram 'notes-mindmap': kind 'sequence' does not match the source: check_diagrams reads a mindmap diagram"; count "FINDING" 1
mut dg-mm-flow "$MM"'["source"] = d["diagrams"][0]["source"]'
run 1 "kind mindmap over a sequence source is a finding" check "$TMP/dg-mm-flow.json" --repo "$REPO"
has "kind 'mindmap' does not match the source: check_diagrams reads a sequence diagram"; count "FINDING" 1
mut dg-mm-indent "$MM"'["source"] = "mindmap\n  root((Notes))\n    Routes\n        GET\n      PATCH"'
run 1 "a mindmap with an in-between dedent is a finding" check "$TMP/dg-mm-indent.json" --repo "$REPO"
has "diagram 'notes-mindmap': mindmap indentation is inconsistent: 'PATCH'"; count "FINDING" 1
mut dg-digits "$DG"'["source"] += "\n  A->>C: retry 3 times, 250 ms apart\n  A->>D: SELECT 1"'
run 0 "digits in a diagram source are code, not bare numbers" check "$TMP/dg-digits.json" --repo "$REPO"
hasnt "bare number"
mut dg-caption-num "$DG"'["caption"]["en"] = "Read top to bottom: 3 calls race."'
run 1 "a bare number in a diagram caption is caught" check "$TMP/dg-caption-num.json" --repo "$REPO"
has "diagrams\[0\].caption.en: bare number '3' in prose"; count "FINDING" 1
mut dg-title-num "$DG"'["title"]["ja"] = "競合 2 件"'
run 1 "a bare number in a diagram title, ja included, is caught" check "$TMP/dg-title-num.json" --repo "$REPO"
has "diagrams\[0\].title.ja: bare number '2'"; count "FINDING" 1
mut dg-ph "$DG"'["caption"]["en"] = "Stale for up to {{cache_ttl}}."'
run 0 "a {{name}} placeholder in a caption passes" check "$TMP/dg-ph.json" --repo "$REPO"
# 31 nodes infers level 3: check_diagrams' step table under the block is not owed here, its
# branch rule still is
BIG='"flowchart TD\n" + "\n".join(f"  n{i} --> n{i+1}" for i in range(30))'
mut dg-big "$DG"'.update(kind="flowchart", tag="inferred", source='"$BIG"' + "\n  n30 --> pick{\"done?\"}")'
run 0 "a level-3 diagram does not owe check_diagrams' step table" check "$TMP/dg-big.json" --repo "$REPO"
hasnt "step table"
mut dg-big-nobranch "$DG"'.update(kind="flowchart", tag="inferred", source='"$BIG"')'
run 1 "a level-3 diagram still owes a shown branch" check "$TMP/dg-big-nobranch.json" --repo "$REPO"
has "diagram 'race-sequence': level 3 requires at least one shown branch"; count "FINDING" 1
mut dg-untyped "$DG"'["source"] = "pie title Notes\n  \"a\" : 1"'
run 1 "a source check_diagrams cannot type is a finding" check "$TMP/dg-untyped.json" --repo "$REPO"
has "diagram 'race-sequence': could not identify a diagram type"; count "FINDING" 1
mut dg-shape 'd["diagrams"] = d["diagrams"][:1]; d["diagrams"].append(dict(d["diagrams"][0])); d["diagrams"][0].update(kind="gantt", scenario="nope", ev=["e-nope"], tag="verified", caption=7); d["diagrams"][1]["sourc"] = d["diagrams"][1].pop("source")'
run 1 "kind, scenario, ev, tag, caption, a duplicate id and an unknown key are findings" check "$TMP/dg-shape.json" --repo "$REPO"
has "diagram 'race-sequence'.kind: must be one of sequence, flowchart, state, er, class, mindmap"
has "diagram 'race-sequence'.scenario: unknown scenario \"nope\""
has "diagram 'race-sequence'.ev: unknown evidence id 'e-nope'"
has "diagram 'race-sequence'.tag: must be 'inferred'"
has "diagram 'race-sequence'.caption: must be text"
has "diagrams\[1\].id: duplicate diagram id 'race-sequence'"
has "diagrams\[1\]: unknown key 'sourc' (did you mean 'source'?)"
mut dg-tagged 'd["diagrams"][0].pop("ev"); d["diagrams"][0]["tag"] = "inferred"'
run 0 "a diagram tagged inferred needs no ev" check "$TMP/dg-tagged.json" --repo "$REPO"
mut dg-notlist 'd["diagrams"] = {"race-sequence": d["diagrams"][0]}'
run 1 "diagrams that are not a list are a finding" check "$TMP/dg-notlist.json" --repo "$REPO"
has "diagrams: must be a list of diagrams"
mut dg-heavy 'd["diagrams"] = [dict(d["diagrams"][0], id="d%d" % i) for i in range(5)]'
run 1 "five diagrams are over the heavy budget" check "$TMP/dg-heavy.json" --repo "$REPO"
has "over budget (heavy): 5 diagrams, max 4"; count "FINDING" 1
mut dg-heavy-ok 'd["diagrams"] = [dict(d["diagrams"][0], id="d%d" % i) for i in range(4)]'
run 0 "four diagrams fit the heavy budget" check "$TMP/dg-heavy-ok.json" --repo "$REPO"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["diagrams"].append(dict(d["diagrams"][0], id="third")); print(json.dumps(d))' "$FIX/all-actions.json" >"$TMP/dg-light.json"
run 1 "three diagrams are over the light budget" check "$TMP/dg-light.json" --repo "$REPO"
has "over budget (light): 3 diagrams, max 2"; count "FINDING" 1

echo "--- the same example under other conditions"
run 1 "example at --tier light is over budget" check "$EX" --repo "$REPO" --tier light
has "over budget (light): 3 scenarios, max 2"
has "over budget (light): 2 outlines, max 1"
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
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["pr"]=1479; d["title"]["en"]="PR 1480 is stacked on this one"; d["subject"]["lede"]["en"]+=" See PR #1497 and #1227."; print(json.dumps(d))' "$EX" >"$TMP/pr-other.json"
run 0 "a reference to another PR or issue (PR 1480, PR #1497, #1227) is not a bare number" check "$TMP/pr-other.json" --repo "$REPO"
hasnt "bare number"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["subject"]["pr"]=1479; d["title"]["en"]="PR 1497 moves 1497 items"; print(json.dumps(d))' "$EX" >"$TMP/pr-qty.json"
run 1 "the same digits as a quantity are still a bare number" check "$TMP/pr-qty.json" --repo "$REPO"
has "title.en: bare number '1497'"; count "FINDING" 1
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
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"]=d["scenarios"][1:]; d.pop("compare", None); d["outline"]=d["outline"][:1]; print(json.dumps(d))' "$EX" >"$LIGHT"
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
             "## Decision", "(chosen)", "| `cache_ttl` | 300 s | verified | `src/notes.js:2` |", "the TTL of 300 s runs out",
             "## Before you watch", "**A reader sees the note an editor just saved", "In this PR:", "Not in this PR:",
             "| GET /notes/:id | route | `race` (A PATCH lands", "## Terms", "| `TTL` | How long a cache entry lives",
             "## Workflow outline", "`getNote(db, cache, id)`, animated in `race`:",
             "cached = cache.get(cacheKey(id))  # step 1", "`race` · race · origin: in-code · severity high",
             "Step 2:\n\n```\nnote = db.query(", "Step 5:\n\n```\ncache.set(cacheKey(id)", "Step 5:\n\n```\ncached_version"):
    assert want in md, want
assert "{{" not in md, "unfilled placeholder in explain.md"
tldr = ("> **What:** Shows how a reader can keep seeing a note an editor has already changed.\n>\n"
        "> **How:** A read fills the cache from the database; an edit writes the database and then clears the cache entry.\n>\n"
        "> **Watch out:** An edit that lands between a read and its cache fill leaves the old note cached until the TTL of 300 s runs out.\n\n"
        "GET reads the cache")
assert md.index("\n\n") + 2 == md.index(tldr), "the tldr block sits right after the H1, then the lede"
assert md.index(tldr) < md.index("| subject |"), "tldr before the lede table"
assert "### The notes service at a glance: its parts, grouped\n\n```mermaid\nmindmap\n  %% level: 1\n  root((Notes service))" in md
assert md.index("## Before you watch") < md.index("## Terms") < md.index("## Diagrams") < md.index("## Workflow outline") < md.index("## Map")
assert md.index("| generated |") < md.index("## Contents") < md.index("## Before you watch"), "Contents sits under the lede table"
contents = md[md.index("## Contents"):md.index("## Before you watch")]
links = re.findall(r"^\| \[(.+?)\]\(#([^)]+)\) \| (.+) \|$", contents, re.M)
after = [h for h in re.findall(r"^## (.+)$", md[md.index("## Before you watch"):], re.M)]
assert [t for t, _, _ in links] == after, (links, after)
for want in ("| [Before you watch](#before-you-watch) | what the change does for a user",
             "| [Diagrams](#diagrams) | the flow at a glance, as diagrams |",
             "| [A PATCH lands between a GET's read and its cache fill](#a-patch-lands-between-a-gets-read-and-its-cache-fill) | race scenario `race`",
             "| [Numbers](#numbers) |"):
    assert want in contents, want
for want in ("### The race as a sequence: who calls whom, in what order\n\n```mermaid\nsequenceDiagram\n  participant R as Reader",
             "  A-->>R: 200 OK, the old note\n```\n\nRead top to bottom.",
             "Animated in `race`. Evidence: `src/routes.js:4`, `src/notes.js:7`"):
    assert want in md, want
assert "What-if:" not in md, "no what-if banner on an in-code issue"
assert data["snippets"] == {}, "no --repo, no snippets"
print("md ok")
PY2
[ $? -eq 0 ] && ok "  page carries tier light; explain.md has tables, hazard, skip, decision, filled numbers" || bad "  light build / md export"
run 0 "build --tier heavy overrides nothing else" build "$BULK" --tier heavy --out "$TMP/real-heavy"
grep -q 'data-tier="heavy"' "$TMP/real-heavy/index.html" && ok "  heavy page carries tier heavy" || bad "  heavy tier missing"
grep -q '^## Plan B under load' "$TMP/real-heavy/explain.md" && ok "  bulk-import explain.md has every scenario" || bad "  bulk md"
python3 - "$TMP/real-heavy/explain.md" >"$OUT/r.out" 2>&1 <<'PY7'
import sys
md = open(sys.argv[1]).read()
assert "## Diagrams\n\n### Plan B as a flow: one file in, three queues out\n\n```mermaid\nflowchart LR\n" in md
assert "Animated in `plan-b`. Evidence: *inferred*" in md
assert "| [Diagrams](#diagrams) |" in md and "| [Before you watch]" not in md, "rows only for sections present"
PY7
[ $? -eq 0 ] && ok "  bulk-import explain.md fences its flowchart, marks it inferred, lists only present sections" || bad "  bulk md diagrams / contents"
python3 "$F" build "$TMP/new/demo-flow.json" --out "$TMP/starter-site" >/dev/null 2>&1
grep -q '^| \[Workflow outline\](#workflow-outline) |' "$TMP/starter-site/explain.md" && ! grep -q 'Diagrams' "$TMP/starter-site/explain.md" \
  && ok "  a page with no diagrams has no Diagrams section or row" || bad "  starter md contents"
! grep -q '^> \*\*What:\*\*' "$TMP/starter-site/explain.md" && ok "  a page with no tldr has no tldr block" || bad "  starter md tldr"
grep -q '^> \*\*Watch out:\*\* Both plans queue' "$TMP/real-heavy/explain.md" && ok "  bulk-import explain.md carries its plain-string tldr" || bad "  bulk md tldr"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["scenarios"][2]["title"]="Map"; d["diagrams"][0]["source"]+="\n  %% a ``` fence in a comment"; print(json.dumps(d))' "$EX" >"$TMP/dup-heading.json"
run 0 "build with a scenario titled like a fixed section" build "$TMP/dup-heading.json" --out "$TMP/dup-heading"
grep -q '^| \[Map\](#map-1) | fix scenario `fix-set-if-fresh`' "$TMP/dup-heading/explain.md" && ok "  a repeated heading links to its -1 anchor" || bad "  duplicate heading anchor"
grep -q '^````mermaid$' "$TMP/dup-heading/explain.md" && ok "  a source holding a fence gets a longer fence" || bad "  fence length"
grep -q '^> What-if: this is not in the code. It shows why the real design is the way it is.$' "$TMP/real-heavy/explain.md" \
  && grep -q 'failure · origin: what-if · severity low' "$TMP/real-heavy/explain.md" \
  && ok "  a what-if issue carries its origin and the what-if banner" || bad "  what-if banner / origin in md"

echo "--- build: real code snippets come from git, never from the scenario"
run 0 "build without --repo still succeeds" build "$EX" --out "$TMP/nosnip"
has "real code for 0 of 12 cited line(s) (no --repo given)"
run 0 "build --repo reads the cited lines from git" build "$EX" --repo "$REPO" --out "$TMP/snip"
hasnt "real code for"
python3 - "$TMP/snip/index.html" "$SHA" >"$OUT/r.out" 2>&1 <<'PY4'
import json, re, sys
page, sha = open(sys.argv[1]).read(), sys.argv[2]
d = json.loads(re.search(r'<script type="application/json" id="flow-data">(.*?)</script>', page, re.S).group(1))
sn = d["snippets"]
g = sn["e-cache-get"]
assert (g["path"], g["sha"], g["start"], g["hl"]) == ("src/notes.js", sha, 4, 7), g
assert len(g["lines"]) == 9 and "cache.get(cacheKey(id))" in g["lines"][g["hl"] - g["start"]], g
t = sn["e-ttl"]
assert (t["start"], t["hl"], len(t["lines"])) == (1, 2, 7), t  # clamped at the top of the file
f = sn["e-fill-if-fresh"]
assert (f["start"], f["hl"], len(f["lines"])) == (2, 5, 7), f  # clamped at the bottom
assert "e-no-version-check" not in sn, "an absence has no snippet"
assert len(sn) == 12, sorted(sn)
print("snippets ok")
PY4
[ $? -eq 0 ] && ok "  snippets: path, pinned sha, line-3..line+5 clamped, the cited line is hl, none for an absence" || bad "  snippet payload"
python3 - "$EX" "$TMP/off-by-one.json" <<'PY5'
import json, sys
d = json.load(open(sys.argv[1]))
d["evidence"]["e-cache-get"]["at"] = "src/notes.js:8"  # one line below the anchor, inside the window
json.dump(d, open(sys.argv[2], "w"))
PY5
run 0 "build --repo with a citation one line off the anchor" build "$TMP/off-by-one.json" --repo "$REPO" --out "$TMP/snip-off"
python3 - "$TMP/snip-off/index.html" >"$OUT/r.out" 2>&1 <<'PY6'
import json, re, sys
d = json.loads(re.search(r'<script type="application/json" id="flow-data">(.*?)</script>', open(sys.argv[1]).read(), re.S).group(1))
g = d["snippets"]["e-cache-get"]
assert g["hl"] == 7 and "cache.get(cacheKey(id))" in g["lines"][g["hl"] - g["start"]], g
PY6
[ $? -eq 0 ] && ok "  snippets: the highlight lands on the line holding the anchor, not the off-by-one cited line" || bad "  snippet highlight follows the anchor"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["evidence"]["e-ttl"]={"at": "web/page.js:2", "anchor": "const page"}; print(json.dumps(d))' "$EX" >"$TMP/snip-esc.json"
run 0 "a cited line holding </script builds" build "$TMP/snip-esc.json" --repo "$REPO" --out "$TMP/snip-esc"
python3 - "$TMP/snip-esc/index.html" >"$OUT/r.out" 2>&1 <<'PY5'
import json, re, sys
page = open(sys.argv[1]).read()
data = re.search(r'<script type="application/json" id="flow-data">(.*?)</script>', page, re.S).group(1)
assert "</" not in data and "<!--" not in data, "unescaped < in snippet data"
assert json.loads(data)["snippets"]["e-ttl"]["lines"][1] == 'const page = "</script><!--";'
print("escape ok")
PY5
[ $? -eq 0 ] && ok "  </script and <!-- inside a snippet line stay escaped and round-trip" || bad "  snippet escaping"

echo "--- optional: the engine renders in headless Chrome (never required)"
CHROME="${FLOW_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
# no network in tests: mermaid never loads, so every run exercises the diagram fallback
NO_NET='--host-resolver-rules=MAP * ~NOTFOUND'
# <page> <width> [#hash]: the JSON tests/flow/smoke-probe.js leaves on <html data-probe>
probe() {
  python3 -c 'import sys; p=open(sys.argv[1]).read(); open(sys.argv[2], "w").write(p.replace("</body>", "<script>" + open(sys.argv[3]).read() + "</script></body>"))' "$1" "$1.probe.html" "$FIX/smoke-probe.js"
  "$CHROME" "$NO_NET" --headless=new --disable-gpu --no-first-run --window-size="$2",900 --virtual-time-budget=5000 --dump-dom "file://$1.probe.html${3:-}" 2>/dev/null \
    | python3 -c 'import html, re, sys; m = re.search(r"data-probe=\"([^\"]*)\"", sys.stdin.read()); print(html.unescape(m.group(1)) if m else "{}")'
}
if [ -x "$CHROME" ]; then
  # the light example is the light-budget variant; bulk-import is over the light budget
  for pair in "$LIGHT:light" "$EX:heavy" "$BULK:heavy"; do
    ex="${pair%:*}"; tier="${pair##*:}"; name="$(basename "$ex" .json) $tier"
    want=$(python3 "$F" reduce "$ex" --json | python3 -c 'import json,sys; print(",".join(f"{k}:{len(v)}" for k,v in json.load(sys.stdin)["scenarios"].items()))')
    site="$TMP/smoke-$(basename "$ex" .json)-$tier"
    python3 "$F" build "$ex" --tier "$tier" --repo "$REPO" --out "$site" >/dev/null 2>&1
    "$CHROME" "$NO_NET" --headless=new --disable-gpu --no-first-run --virtual-time-budget=5000 --dump-dom "file://$site/index.html" >"$OUT/r.out" 2>/dev/null
    tagline=$(grep -o '<html[^>]*>' "$OUT/r.out" | head -1)
    case "$tagline" in
      *data-flow-error*) bad "smoke $name: data-flow-error set" ;;
      *'data-flow-ok="true"'*"data-flow-steps=\"$want\""*|*"data-flow-steps=\"$want\""*'data-flow-ok="true"'*) ok "smoke $name: rendered, steps $want" ;;
      *) bad "smoke $name: no data-flow-ok with steps $want ($tagline)" ;;
    esac
    for w in 1280 400; do
      probe "$site/index.html" "$w" >"$OUT/probe.json"; cp "$OUT/probe.json" "$OUT/r.out"
      python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("crossings")); sys.exit(0 if d.get("ok") == "true" and d.get("crossings") == [] else 1)' "$OUT/probe.json" >>"$OUT/r.out" 2>&1 \
        && ok "  smoke $name at ${w}px: no map edge passes through a box it does not connect" || bad "  smoke $name at ${w}px: an edge crosses a box"
      python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("problems")); sys.exit(0 if d.get("problems") == [] else 1)' "$OUT/probe.json" >>"$OUT/r.out" 2>&1 \
        && ok "  smoke $name at ${w}px: page sections meet the contract" || bad "  smoke $name at ${w}px: a page section breaks its contract"
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
  # heavy, opened at a step that outline lines point to: the outline highlight and the code pane follow it
  probe "$TMP/smoke-stale-writeback-heavy/index.html" 1280 "#race.4" >"$OUT/probe.json"; cp "$OUT/probe.json" "$OUT/r.out"
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("problems")); sys.exit(0 if d.get("ok") == "true" and d.get("problems") == [] and d["facts"].get("outlineCur") else 1)' "$OUT/probe.json" >>"$OUT/r.out" 2>&1 \
    && ok "  smoke heavy #race.4: outline lines and code pane meet the contract" || bad "  smoke heavy #race.4: a page section breaks its contract"
  probe "$TMP/smoke-stale-writeback-light-light/index.html" 1280 "#%E0%A4%A" >"$OUT/r.out"
  grep -q '"ok": *"true"' "$OUT/r.out" && ok "  smoke light: a malformed %-escape in the hash still renders" || bad "  smoke light: a malformed hash breaks the page"
else
  echo "  SKIP headless smoke: Google Chrome not found (set FLOW_CHROME to a Chrome binary)"
fi

echo
echo "flow: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
