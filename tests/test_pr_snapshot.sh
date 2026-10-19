#!/usr/bin/env bash
# pr_snapshot.py (pins + exports a PR from a bare remote, never touches the clone's work tree)
# and pr_suggest.py (applies each suggestion/diff of the golden run to that head), then the
# gate with --snap (G10) on the result. No network: the "remote" is a local bare repo that
# publishes refs/pull/9999/head the way GitHub does.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIX="$ROOT/evals/fixtures/pr-review/example-run"
PRD="PR-9999__backend-reset-rate-limit__dana"
TMP="$(cd "$(mktemp -d)" && pwd -P)"; OUT="$(mktemp -d)"
trap 'rm -rf "$TMP" "$OUT"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-64s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "$1"; sed 's/^/       /' "$OUT/r.out" | head -12; }
run() {
  local exp="$1" label="$2" tool="$3"; shift 3
  python3 "$ROOT/scripts/$tool.py" "$@" >"$OUT/r.out" 2>&1; local got=$?
  [ "$got" -eq "$exp" ] && ok "$label" || bad "$label (exit exp=$exp got=$got)"
}
has()   { grep -q -- "$1" "$OUT/r.out" && ok "  reports $1" || bad "  NOT reported: $1"; }
hasnt() { grep -q -- "$1" "$OUT/r.out" && bad "  unexpectedly reports $1" || ok "  does not report $1"; }

export GIT_CONFIG_GLOBAL="$TMP/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --global user.email t@t; git config --global user.name t; git config --global init.defaultBranch trunk

# --- a remote whose default branch is "trunk", with PR 9999 published under refs/pull/
git init -q --bare "$TMP/remote.git"
git clone -q "$TMP/remote.git" "$TMP/author" 2>/dev/null
cd "$TMP/author"
mkdir -p src/reset
cat > src/reset/reset.controller.spec.ts <<'EOF'
import { ResetLimiter } from './limiter';

describe('ResetLimiter', () => {
  it('allows the first call', () => {
    const l = new ResetLimiter();
    expect(l.allow('198.51.100.7', 'user@acme.test', 0)).toBe(true);
  });
});
EOF
git add -A; git commit -qm base; git push -q origin trunk 2>/dev/null
git checkout -qb dana/reset-cap
cat > src/reset/limiter.ts <<'EOF'
// Password-reset mail limiter.
export const WINDOW_MS = 60000;
export const MAX_MAILS = 3;

export class ResetLimiter {
  private readonly hits = new Map<string, number[]>();

  allow(ip: string, email: string, now: number): boolean {
    // one bucket per sender
    const key = `reset:${ip}`;
    const recent = (this.hits.get(key) ?? []).filter((t) => now - t < 60000);
    if (recent.length >= 3) return false;
    this.hits.set(key, [...recent, now]);
    return true;
  }
}
EOF
git add -A; git commit -qm "cap reset mails"
HEAD_SHA="$(git rev-parse HEAD)"
git push -q origin HEAD:refs/pull/9999/head 2>/dev/null
git switch -q trunk; echo "more" > NOTES.md; git add -A; git commit -qm "base moves on"; git push -q origin trunk 2>/dev/null

# --- the reviewer's clone: remote named "upstream" (not origin), plus an unrelated fork remote
git clone -q -o upstream "$TMP/remote.git" "$TMP/clone" 2>/dev/null
git -C "$TMP/clone" remote add fork "$TMP/elsewhere.git"
echo "local edit" > "$TMP/clone/WIP.txt"
BEFORE="$(git -C "$TMP/clone" status --porcelain; git -C "$TMP/clone" rev-parse HEAD)"

echo "== snapshot"
SNAP="$TMP/snap"
run 0 "snapshot PR 9999" pr_snapshot --repo "$TMP/clone" --pr 9999 --dest "$SNAP"
has "| 9999 | \`trunk\` |"; has "$HEAD_SHA"
[ -f "$SNAP/9999/src/reset/limiter.ts" ] && ok "  head tree exported" || bad "  no head tree"
[ -f "$SNAP/base-9999/src/reset/reset.controller.spec.ts" ] && [ ! -f "$SNAP/base-9999/src/reset/limiter.ts" ] \
  && ok "  merge-base tree exported" || bad "  merge-base tree wrong"
[ -f "$SNAP/trunk/NOTES.md" ] && ok "  default branch detected (trunk, not main)" || bad "  default branch tree missing"
grep -q '^+++ b/src/reset/limiter.ts' "$SNAP/9999.diff" && ok "  diff written" || bad "  diff missing"
grep -q "| 1 | 1 | 1 |" "$SNAP/PINS.md" && ok "  commits / files / behind counted" || { cp "$SNAP/PINS.md" "$OUT/r.out"; bad "  counts wrong"; }
AFTER="$(git -C "$TMP/clone" status --porcelain; git -C "$TMP/clone" rev-parse HEAD)"
[ "$BEFORE" = "$AFTER" ] && ok "  clone work tree and HEAD untouched" || bad "  snapshot changed the clone"
run 0 "remote picked by --url" pr_snapshot --repo "$TMP/clone" --pr 9999 --dest "$TMP/snap2" --url "$TMP/remote.git"
run 1 "--remote that does not exist" pr_snapshot --repo "$TMP/clone" --pr 9999 --dest "$TMP/snap3" --remote origin
has "no remote named 'origin'"
run 1 "a PR the remote does not publish" pr_snapshot --repo "$TMP/clone" --pr 4242 --dest "$TMP/snap4"
run 1 "not a git repository" pr_snapshot --repo "$TMP/snap" --pr 9999 --dest "$TMP/snap5"
run 2 "--pr is required" pr_snapshot --repo "$TMP/clone" --dest "$TMP/snap6"

echo "== suggestions"
RUN="$TMP/run"; cp -R "$FIX" "$RUN"; D="$RUN/$PRD"
run 0 "pr_suggest from the snapshot" pr_suggest "$D" --repo "$TMP/clone" --snap "$SNAP" --note "no node_modules in the snapshot" --write
has "9999-BUG-01      suggestion applies cleanly"; has "9999-TST-01      diff       applies cleanly"; has "9999-CNV-01      diff       applies cleanly"
cmp -s "$D/suggestion-checks.json" "$FIX/$PRD/suggestion-checks.json" && ok "  proof matches the golden run" || bad "  suggestion-checks.json differs"
python3 - "$D/review.json" "$HEAD_SHA" <<'PY'
import json, sys; p = sys.argv[1]; r = json.load(open(p)); r["pr"]["head_sha"] = sys.argv[2]; json.dump(r, open(p, "w"), indent=2)
PY
run 0 "pr_suggest from git archive of pr.head_sha" pr_suggest "$D" --repo "$TMP/clone" --note "no node_modules in the snapshot"
has "9999-CNV-01      diff       applies cleanly"
run 0 "--cmd runs without a shell" pr_suggest "$D" --repo "$TMP/clone" --cmd "grep -q email.toLowerCase src/reset/limiter.ts"
has "9999-BUG-01      suggestion typecheck ok"; has "9999-CNV-01      diff       not checked — typecheck failed"
run 0 "a shell metacharacter is an argument, not a pipeline" pr_suggest "$D" --repo "$TMP/clone" --cmd "true; touch $TMP/pwned"
[ ! -e "$TMP/pwned" ] && ok "  nothing ran through a shell" || bad "  --cmd went through a shell"
python3 - "$D/review.json" <<'PY'
import json, sys; p = sys.argv[1]; r = json.load(open(p))
i = [x for x in r["items"] if x["id"] == "9999-CNV-01"][0]
i["change"]["body"] = i["change"]["body"].replace("filter((t) => now - t < 60000)", "filter((t) => now - t < 59999)", 1)
json.dump(r, open(p, "w"), indent=2)
PY
run 0 "a diff whose - line is not in the file" pr_suggest "$D" --repo "$TMP/clone" --note x --write
has "9999-CNV-01      diff       not checked — does not apply"
python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); i=[x for x in r["items"] if x["id"]=="9999-CNV-01"][0]; assert i["change"]["type"]=="pseudo"' "$D/review.json" \
  && ok "  --write downgrades it to pseudo" || bad "  not downgraded"
ls "$TMP/clone" | grep -q . && [ "$BEFORE" = "$(git -C "$TMP/clone" status --porcelain; git -C "$TMP/clone" rev-parse HEAD)" ] \
  && ok "  clone untouched by pr_suggest" || bad "  pr_suggest changed the clone"
run 2 "no review.json" pr_suggest "$TMP" --repo "$TMP/clone"

echo "== gate with --snap"
G="$TMP/gate"; cp -R "$FIX" "$G"
run 0 "golden run is consistent with the snapshot" pr_review_gate "$G" --snap "$SNAP" --no-render-mermaid
hasnt "G10-snapshot"
python3 - "$G/$PRD/review.json" <<'PY'
import json, sys; p = sys.argv[1]; r = json.load(open(p))
i = [x for x in r["items"] if x["id"] == "9999-TST-01"][0]; i["where"]["path"] = "src/reset/missing.ts"
json.dump(r, open(p, "w"), indent=2)
PY
python3 "$ROOT/scripts/pr_review.py" render "$G/$PRD" >/dev/null
run 1 "a path missing at the pinned head" pr_review_gate "$G" --snap "$SNAP" --no-render-mermaid
has "G10-snapshot"
run 2 "--snap that does not exist" pr_review_gate "$G" --snap "$TMP/nosnap"

echo
echo "pr_snapshot: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
