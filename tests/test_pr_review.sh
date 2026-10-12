#!/usr/bin/env bash
# pr_review.py (review root resolution, init, CONTEXT.md refresh, render, index, find, emit)
# and pr_review_gate.py (passes the golden example run, catches each seeded break).
# The golden run is evals/fixtures/pr-review/example-run (fictional PR 9999).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIX="$ROOT/evals/fixtures/pr-review/example-run"
PRD="PR-9999__backend-reset-rate-limit__dana"
TMP="$(cd "$(mktemp -d)" && pwd -P)"; OUT="$(mktemp -d)"
trap 'rm -rf "$TMP" "$OUT"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-64s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "$1"; sed 's/^/       /' "$OUT/r.out" | head -12; }
# run <exp-exit> <label> <tool> [args...]
run() {
  local exp="$1" label="$2" tool="$3"; shift 3
  python3 "$ROOT/scripts/$tool.py" "$@" >"$OUT/r.out" 2>&1; local got=$?
  [ "$got" -eq "$exp" ] && ok "$label" || bad "$label (exit exp=$exp got=$got)"
}
has()  { grep -q -- "$1" "$OUT/r.out" && ok "  reports $1" || bad "  NOT reported: $1"; }
hasnt() { grep -q -- "$1" "$OUT/r.out" && bad "  unexpectedly reports $1" || ok "  does not report $1"; }
# same <label> <expected> : compares the whole output of the last run
same() { [ "$(cat "$OUT/r.out")" = "$2" ] && ok "$1" || { bad "$1"; echo "       want: $2"; }; }

export PR_REVIEW_HOME="$TMP/home"; unset PR_REVIEW_OUT
export GIT_CONFIG_GLOBAL="$TMP/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --global user.email t@t; git config --global user.name t; git config --global init.defaultBranch main
WS="$(cd "$TMP" && pwd -P)/ws"; mkdir -p "$WS"
mkrepo() { mkdir -p "$1" && git -C "$1" init -q && echo x > "$1/f" && git -C "$1" add f && git -C "$1" commit -qm init; }

echo "== out-dir resolution"
mkrepo "$WS/app"; git -C "$WS/app" remote add origin git@github.com:acme/widgets.git
run 0 "default: <parent>/code-review/<remote repo name>" pr_review out-dir --repo "$WS/app"
same "  prints the absolute path" "$WS/code-review/widgets"
git -C "$WS/app" worktree add -q "$WS/app-wt" -b wt 2>/dev/null
run 0 "worktree maps to its main repo" pr_review out-dir --repo "$WS/app-wt"
same "  same root as the main repo" "$WS/code-review/widgets"
mkrepo "$WS/plain"
run 0 "no remote: folder name" pr_review out-dir --repo "$WS/plain"
same "  uses the folder name" "$WS/code-review/plain"
run 0 "--out wins" pr_review out-dir --repo "$WS/app" --out "$TMP/explicit"
same "  prints --out" "$TMP/explicit"
git -C "$WS/app" config pr-review.out "$TMP/from-git-config"
run 0 "git config pr-review.out" pr_review out-dir --repo "$WS/app-wt"
same "  read through the worktree" "$TMP/from-git-config"
PR_REVIEW_OUT="$TMP/from-env" python3 "$ROOT/scripts/pr_review.py" out-dir --repo "$WS/app" >"$OUT/r.out" 2>&1
same "env PR_REVIEW_OUT beats git config" "$TMP/from-env"
git -C "$WS/app" config --unset pr-review.out
mkdir -p "$PR_REVIEW_HOME"; printf '{"out": "%s"}\n' "$TMP/from-user-config" > "$PR_REVIEW_HOME/config.json"
run 0 "user config.json out" pr_review out-dir --repo "$WS/app"
same "  prints config out" "$TMP/from-user-config"
mv "$PR_REVIEW_HOME/config.json" "$PR_REVIEW_HOME/config.off"
run 0 "no clone: user fallback from the PR URL" pr_review out-dir --url https://git.example.com/acme/widgets/pull/12
same "  <home>/reviews/<host>/<owner>/<repo>" "$PR_REVIEW_HOME/reviews/git.example.com/acme/widgets"
mkdir -p "$TMP/mono"; git -C "$TMP/mono" init -q; mkrepo "$TMP/mono/inner"
git -C "$TMP/mono/inner" remote add origin https://github.com/acme/inner.git
run 0 "parent inside a git work tree: user fallback" pr_review out-dir --repo "$TMP/mono/inner"
same "  never writes into the outer repo" "$PR_REVIEW_HOME/reviews/github.com/acme/inner"
run 0 "--json" pr_review out-dir --repo "$WS/app" --json
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert sorted(d)==["cr","meta","profile","source_of_rule"], d; assert d["meta"].endswith("/widgets/_meta")' "$OUT/r.out" \
  && ok "  keys cr, meta, profile, source_of_rule" || bad "  wrong --json keys"
run 0 "paths --json" pr_review paths --repo "$WS/app" --json
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["context"].endswith("/widgets/CONTEXT.md"); assert set(d["meta_files"])=={"focus.md","decisions.md","settings.json"}' "$OUT/r.out" \
  && ok "  context path + meta files" || bad "  paths --json incomplete"
run 2 "--repo that does not exist is refused" pr_review out-dir --repo "$TMP/nope"
run 2 "no subcommand is a usage error" pr_review

echo "== init + CONTEXT.md"
printf '{"name":"w"}\n' > "$WS/app/package.json"; : > "$WS/app/pnpm-lock.yaml"; printf '# rules\n' > "$WS/app/AGENTS.md"
mkdir -p "$WS/app/.github/skills/style" "$WS/app/src"; printf -- '---\nname: style\n---\n' > "$WS/app/.github/skills/style/SKILL.md"
git -C "$WS/app" add -A; git -C "$WS/app" commit -qm stack
mkrepo "$WS/sibling"; git -C "$WS/sibling" remote add origin https://github.com/acme/sibling.git
mkrepo "$WS/other"; git -C "$WS/other" remote add origin https://github.com/someone-else/other.git
CR="$WS/code-review/widgets"
run 0 "init scaffolds the review root" pr_review init --repo "$WS/app"
for f in CONTEXT.md INDEX.md _meta/focus.md _meta/decisions.md _meta/settings.json; do
  [ -f "$CR/$f" ] && ok "  created $f" || bad "  missing $f"
done
[ "$(cat "$CR/_meta/settings.json")" = "{}" ] && ok "  settings.json is {}" || bad "  settings.json content"
grep -q "| Date | Decision | Source | Applies to |" "$CR/_meta/decisions.md" && ok "  decisions table header" || bad "  decisions table header"
C="$CR/CONTEXT.md"; cp "$C" "$OUT/r.out"
has "| Owner / repo | acme/widgets |"; has "pnpm"; has "Node.js"; has "\`AGENTS.md\`"; has ".github/skills/style/SKILL.md"
has "\`sibling\` → github.com/acme/sibling"; hasnt "someone-else"; has "<!-- fill:"; has "HEAD \`$(git -C "$WS/app" rev-parse HEAD)\`"
grep -q "No reviews yet" "$CR/INDEX.md" && ok "  INDEX.md is the empty index" || bad "  INDEX.md not the empty index"
printf 'repo rule: money is integer cents\n' >> "$CR/_meta/focus.md"
sed -i.bak 's/<!-- fill: the 3-5 decisions.*-->/We ship behind flags./' "$C" && rm -f "$C.bak"
cp "$C" "$TMP/context.before"
run 0 "init again" pr_review init --repo "$WS/app"
has "0 file(s) created"
grep -q "integer cents" "$CR/_meta/focus.md" && cmp -s "$C" "$TMP/context.before" && ok "  never overwrites an existing file" || bad "  init overwrote a file"
rm -rf "$WS/code-review/plain"
run 0 "out-dir --ensure runs init" pr_review out-dir --repo "$WS/plain" --ensure
[ -f "$WS/code-review/plain/CONTEXT.md" ] && [ "$(cat "$OUT/r.out")" = "$WS/code-review/plain" ] && ok "  scaffolded, prints only the path" || bad "  --ensure"
printf '# how to contribute\n' > "$WS/app/CONTRIBUTING.md"; git -C "$WS/app" add -A; git -C "$WS/app" commit -qm contrib
run 0 "context --refresh" pr_review context --refresh "$CR"
cp "$C" "$OUT/r.out"
has "\`CONTRIBUTING.md\`"; has "HEAD \`$(git -C "$WS/app" rev-parse HEAD)\`"; has "We ship behind flags."
has "<!-- fill: the labels"
run 0 "context --refresh twice is a no-op" pr_review context --refresh "$CR"
has "already current"
python3 - "$C" <<'PY'
import sys; p = sys.argv[1]; t = open(p).read(); open(p, "w").write(t.replace("<!-- auto:end -->", "", 1))
PY
run 1 "a lost auto marker is refused, not guessed" pr_review context --refresh "$CR"
has "auto block"

echo "== render + index against the golden run"
RUN="$TMP/cr/password-reset"; mkdir -p "$TMP/cr"; cp -R "$FIX" "$RUN"
run 0 "render <pr-dir>" pr_review render "$RUN/$PRD"
diff -r "$FIX" "$RUN" >"$OUT/r.out" && ok "  output is byte-identical to the golden run" || bad "  render drifted from the golden run"
run 0 "render <review.json>" pr_review render "$RUN/$PRD/review.json"
run 0 "feature <run-root>" pr_review feature "$RUN"
diff -r "$FIX" "$RUN" >"$OUT/r.out" && ok "  run-root README unchanged" || bad "  feature README drifted"
mkdir -p "$TMP/cr/_meta"; cp -R "$FIX/$PRD" "$TMP/cr/_meta/ignored"
run 0 "index <CR>" pr_review index "$TMP/cr"
cp "$TMP/cr/INDEX.md" "$OUT/r.out"; has "widgets PR 9999"; has "password-reset/$PRD/README.md"; hasnt "_meta"
run 0 "find by PR URL" pr_review find "$TMP/cr" https://git.example.com/acme/widgets/pull/9999/changes
has "^v3	$RUN/$PRD	0a1b2c3d"
run 0 "find by folder + number" pr_review find "$TMP/cr" password-reset 9999
run 1 "find: never reviewed" pr_review find "$TMP/cr" https://git.example.com/acme/widgets/pull/1
run 1 "find: no review root yet" pr_review find "$TMP/none" https://git.example.com/acme/widgets/pull/1
run 0 "slug" pr_review slug feature/Reset-Cap; same "  kebab-case last segment" "reset-cap"
run 0 "next-run" pr_review next-run "$RUN"; has "$RUN/runs/"
run 0 "merge a security fragment" pr_review merge "$RUN/$PRD" "$ROOT/scripts/data/pr_review_security_fragment.json"
has "9999-SEC-101"
python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert "9999-SEC-101" not in [i["id"] for i in r["items"]]' "$RUN/$PRD/review.json" \
  && ok "  same_as item is not duplicated" || bad "  same_as item was merged in"
cp -R "$FIX/$PRD" "$TMP/emit"
run 0 "emit draft" pr_review emit "$TMP/emit" draft
python3 "$ROOT/scripts/pr_review.py" emit "$TMP/emit" draft 2>/dev/null >"$OUT/r.out"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["commit_id"]=="0a1b2c3d4e5f60718293a4b5c6d7e8f901234567" and "event" not in d and d["comments"]' "$OUT/r.out" \
  && ok "  draft payload: commit_id, inline comments, no event" || bad "  draft payload"
run 0 "mark-posted" pr_review mark-posted "$TMP/emit" https://git.example.com/acme/widgets/pull/9999#pullrequestreview-1 draft
run 3 "emit after everything is posted: nothing new (exit 3)" pr_review emit "$TMP/emit" draft
run 1 "mark-posted refuses a URL off this PR" pr_review mark-posted "$TMP/emit" https://git.example.com/acme/other/pull/1 draft

echo "== gate"
run 0 "golden run passes" pr_review_gate "$FIX" --no-render-mermaid
has "PASS  rules"; has "PASS  mermaid"; has "WARN  mermaid render skipped"
run 0 "golden PR folder passes" pr_review_gate "$FIX/$PRD" --no-render-mermaid
SHIM="$TMP/shim"; mkdir -p "$SHIM"; ln -s "$(command -v python3)" "$SHIM/python3"
PATH="$SHIM" python3 "$ROOT/scripts/pr_review_gate.py" "$FIX" >"$OUT/r.out" 2>&1
[ $? -eq 0 ] && ok "no npx on PATH: still passes" || bad "no npx on PATH failed the gate"
has "npx not found"
# break <label> <tag> <shell snippet run inside a fresh copy of the PR folder>
brk() {
  local label="$1" tag="$2" snippet="$3" B="$TMP/brk-$RANDOM"
  cp -R "$FIX" "$B"; ( cd "$B/$PRD" && eval "$snippet" )
  python3 "$ROOT/scripts/pr_review_gate.py" "$B" --no-render-mermaid >"$OUT/r.out" 2>&1; local got=$?
  [ "$got" -eq 1 ] && grep -q -- "$tag" "$OUT/r.out" && ok "catches: $label ($tag)" || bad "misses: $label ($tag, exit $got)"
}
brk "hand-edited rendered README" "G11-rendered" 'printf "\nextra\n" >> README.md'
brk "missing 1-context.md" "G0-files" 'mv 1-context.md ../ctx.bak'
brk "wrong recommendation" "G6-recommendation" 'python3 - <<PY
import json; r = json.load(open("review.json")); r["summary"]["recommendation"] = "approve"; json.dump(r, open("review.json", "w"), indent=2)
PY'
brk "inferred evidence without confirm_by" "G2-item" 'python3 - <<PY
import json; r = json.load(open("review.json")); i = r["items"][0]; i["evidence"]["type"] = "inferred"; i["confirm_by"] = None; json.dump(r, open("review.json", "w"), indent=2)
PY'
brk "head SHA not 40-hex" "G7-links" 'python3 - <<PY
import json; r = json.load(open("review.json")); r["pr"]["head_sha"] = "abc123"; json.dump(r, open("review.json", "w"), indent=2)
PY'
brk "an ok-claim without suggestion-checks proof" "G5-checked" 'printf "{}\n" > suggestion-checks.json'
brk "HTML tag in a mermaid node" "\[mermaid\]" 'printf "\n\`\`\`mermaid\nflowchart LR\n    A[\"<b>x</b>\"] --> B\n\`\`\`\n" >> 1-context.md'
brk "unclosed subgraph" "never closed" 'printf "\n\`\`\`mermaid\nflowchart LR\n    subgraph S\n    A --> B\n\`\`\`\n" >> 1-context.md'
brk "semicolon in a sequence diagram" "sequence diagram" 'printf "\n\`\`\`mermaid\nsequenceDiagram\n    A->>B: one; two\n\`\`\`\n" >> 1-context.md'
run 2 "a folder that is no review is a usage error" pr_review_gate "$TMP/ws"

echo
echo "pr_review: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
