#!/usr/bin/env bash
# Regression suite for testplan.py: every detection paired with a clean input that must
# NOT be flagged. trace's false-positive guards (tags in non-test files, commented-out
# and skipped tests) are the half that keeps it from reporting coverage that is not there.
# Run: bash tests/test_testplan.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
TX="$ROOT/bin/100x"
cd "$TMP"

PASS=0; FAIL=0
expect() { # expect <exit> <label> <args...>
  local exp="$1" label="$2"; shift 2
  "$TX" testplan "$@" >$OUT/tp.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-66s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-66s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' $OUT/tp.out; fi
}
has() { grep -qE -- "$1" $OUT/tp.out && { PASS=$((PASS+1)); printf '  ok   %-66s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-66s\n' "NOT reported: $1"; sed 's/^/       /' $OUT/tp.out; }; }
nothas() { grep -qE -- "$1" $OUT/tp.out && { FAIL=$((FAIL+1)); printf '  FAIL %-66s\n' "false positive: $1"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-66s\n' "absent (correct): $1"; }; }

cat > spec.md <<'EOF'
# Spec
## Acceptance criteria
- **AC-1** A member can tag up to 10 people on a photo from the photo page.
| AC-2 | Only the album owner can delete a tag. |
AC-3: A draft album moves to published once the owner confirms.
- **AC-4** A comment must be between 1 and 280 characters.
See AC-2 for the owner rule (a mention, not a definition).
## 0b. Implicit requirements
| id | requirement |
|---|---|
| `web.reflow-320` | no horizontal scroll at 320 CSS px |
| `api.p95-budget` | p95 under 300 ms |
| `a11y.wcag22-aa` | axe-clean at WCAG 2.2 AA |
EOF

# ======================================================================= new
expect 0 "new: spec with ACs generates a plan" new spec.md
has "^\| TC-1-1 \| AC-1 \| e2e \| equivalence partition \(valid\)"
has "\| TC-1-[0-9]+ \| AC-1 \| unit \| boundary value \| value = 11 \| rejected.*max\+1"
has "\| AC-1 \| unit \| boundary value \| value = 10 \| accepted \(max\)"
has "\| AC-4 \| unit \| boundary value \| value = 0 \| rejected"
has "\| AC-4 \| unit \| boundary value \| value = 281 \| rejected"
has "\| AC-2 \| integration \| negative / authz \|"
has "\| AC-3 \| integration \| state transition \(illegal\) \|"
has "\| AC-1 \| [a-z]+ \| equivalence partition \(invalid\) \|"
has "\| TC-web.reflow-320-1 \| web.reflow-320 \| e2e \|"
has "\| TC-api.p95-budget-1 \| api.p95-budget \| load \|"
has "\| TC-a11y.wcag22-aa-1 \| a11y.wcag22-aa \| a11y \|"
has "^\| case id \| AC id \| level \| technique \| input / precondition \| expected \| automated\? \| owner \|"
has "4 acceptance criteria, 3 implicit requirements"
nothas "\| AC-2 \| unit \| boundary value \| value ="     # no numbers in AC-2: no boundary rows
nothas "\| AC-4 \| integration \| state transition"       # no state words in AC-4
nothas "AC-5"                                             # the 'See AC-2' line defined nothing new

expect 2 "new --out refuses to write outside a git repo" new spec.md --out plans/p.md
has "not inside a git repository"
[ ! -e plans ] && { PASS=$((PASS+1)); echo "  ok   nothing written outside a repo"; } || { FAIL=$((FAIL+1)); echo "  FAIL wrote outside a repo"; }
git init -q
expect 0 "new --out --dry-run writes nothing" new spec.md --out plans/p.md --dry-run
has "would write plans/p.md"
[ ! -e plans ] && { PASS=$((PASS+1)); echo "  ok   --dry-run created no file"; } || { FAIL=$((FAIL+1)); echo "  FAIL --dry-run wrote a file"; }
expect 0 "new --out writes the file" new spec.md --out plans/p.md
[ -f plans/p.md ] && grep -q "TC-4-1" plans/p.md && { PASS=$((PASS+1)); echo "  ok   --out file contains cases"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL --out file missing or empty"; }
expect 2 "new --out refuses to overwrite without --force" new spec.md --out plans/p.md
expect 0 "new --out --force overwrites" new spec.md --out plans/p.md --force

printf '# Spec\n\nUsers should be able to tag photos. Acceptance: it works.\n' > noac.md
expect 1 "new: doc without AC ids exits 1" new noac.md
has "no acceptance criteria found"
has "\*\*AC-1\*\*"                                        # tells the author the format
expect 1 "trace: doc without AC ids exits 1" trace noac.md --tests .
expect 2 "new: missing file exits 2" new nope.md

printf '# Spec\n```\nAC-9: inside a code fence is an example, not a criterion\n```\n' > fenced.md
expect 1 "new: AC inside a code fence is not a definition" new fenced.md

# ===================================================================== trace
mkdir -p t/e2e t/api src t/.maestro t/node_modules/pkg
cat > t/e2e/tag.spec.ts <<'EOF'
import { test, expect } from '@playwright/test';
test('AC-1 tags ten people', { tag: '@critical' }, async ({ page }) => {
  await expect(page.getByRole('list')).toBeVisible();
});
// test('AC-3 publishing a draft', async ({ page }) => {
//   await expect(page.getByText('Published')).toBeVisible();
// });
/*
test('AC-3 block-commented test', async () => {
  expect(1).toBe(1);
});
*/
test.skip('AC-4 comment length', async () => { expect(1).toBe(1); });
EOF
cat > t/api/test_delete.py <<'EOF'
# Covers AC-2 (owner-only delete)
def test_non_owner_cannot_delete(client):
    assert client.delete("/tags/1").status_code == 403
EOF
printf '// AC-3 AC-4 mentioned in a helper, not a test\nexport const X = 1;\n' > t/e2e/helpers.ts
printf '# AC-3\nCOMMENT_MAX = 280  # AC-4\n' > t/api/fixtures.py
printf 'AC-3 described in a README\n' > t/README.md
printf '// AC-3 in vendored code\ntest("AC-3", () => {});\n' > t/node_modules/pkg/x.test.js

expect 1 "trace: partial coverage exits 1" trace spec.md --tests t
has "covered   AC-1"
has "t/e2e/tag.spec.ts:2"
has "covered   AC-2"
has "t/api/test_delete.py:1"
has "UNCOVERED AC-3"
has "UNCOVERED AC-4"
has "tag.spec.ts:13 \(skipped test"
has "uncovered: AC-3, AC-4"
has "AC tag\(s\) in non-test files ignored"
nothas "helpers.ts"                 # non-test file
nothas "fixtures.py"                # non-test file
nothas "tag.spec.ts:5"              # line-commented test
nothas "tag.spec.ts:9"              # block-commented test
nothas "node_modules"               # vendored dir skipped

expect 1 "trace --json: partial coverage exits 1" trace spec.md --tests t --json
python3 - "$OUT/tp.out" <<'EOF' && { PASS=$((PASS+1)); echo "  ok   --json is valid and lists uncovered AC-3, AC-4"; } || { FAIL=$((FAIL+1)); echo "  FAIL --json shape"; }
import json, sys
d = json.load(open(sys.argv[1]))
assert d["uncovered"] == ["AC-3", "AC-4"], d["uncovered"]
c = {x["id"]: x for x in d["criteria"]}
assert c["AC-1"]["covered"] and c["AC-1"]["locations"]
assert c["AC-4"]["skipped"] and not c["AC-4"]["covered"]
EOF

cat > t/e2e/publish.test.tsx <<'EOF'
import { it, expect } from 'vitest';
it('publishes a draft once confirmed @AC-3', () => { expect(true).toBe(true); });
EOF
cat > t/.maestro/comment.yaml <<'EOF'
appId: com.example.app
tags:
  - AC-4
---
- launchApp
EOF
cat > t/api/limits_test.go <<'EOF'
package api
// AC-99 references an id the spec never defined
func TestCommentLimit(t *testing.T) {}
EOF
expect 0 "trace: all ACs covered exits 0 (vitest @tag + maestro tags)" trace spec.md --tests t
has "4/4 ACs covered"
has "publish.test.tsx:2"
has "comment.yaml:3"
has "WARN tag for an AC the spec does not define: .*AC-99"

mkdir -p t2
printf "test('AC-1 x', () => { expect(1).toBe(1) })\n" > t2/a.test.js
printf "test('AC-2 x', () => { expect(1).toBe(1) })\n" > t2/b.test.js
expect 1 "trace: comma-separated dirs combine (AC-3, AC-4 still missing)" trace spec.md --tests t2,t/api
has "covered   AC-1"
has "covered   AC-2"
expect 2 "trace: nonexistent --tests dir exits 2, never a silent pass" trace spec.md --tests does-not-exist

# ==================================================================== matrix
expect 0 "matrix mobile prints ASK for min OS" matrix --work mobile --tier small
has "min supported iOS version \| ASK"
has "min supported Android API level \| ASK"
has "^ASK \(must be answered"
has "WCAG 2.2 AA"
expect 0 "matrix web-ui prints the browser + viewport set" matrix --work web-ui --tier growth
has "Desktop Safari \| every PR"
has "iPhone 12"
has "Pixel 5"
has "\| 320 \|"
has "\| 768 \|"
has "\| 1280\+ \|"
has "not dead"
nothas "^ASK"                                            # web defaults need no question
expect 0 "matrix --json is valid" matrix --work mobile --tier prototype --json
python3 -c "import json,sys; d=json.load(open('$OUT/tp.out')); assert len(d['ask'])==3" \
  && { PASS=$((PASS+1)); echo "  ok   matrix --json lists 3 ASK items"; } || { FAIL=$((FAIL+1)); echo "  FAIL matrix --json"; }
expect 2 "matrix rejects an unknown tier" matrix --work web-ui --tier huge

# ================================================================= templates
T="$ROOT/templates/qa"
tpl() { # tpl <file> <required substring>...
  local f="$T/$1"; shift
  [ -f "$f" ] || { FAIL=$((FAIL+1)); echo "  FAIL template missing: $f"; return; }
  for s in "$@"; do
    grep -qF -- "$s" "$f" && PASS=$((PASS+1)) || { FAIL=$((FAIL+1)); echo "  FAIL $f lacks: $s"; }
  done
  printf '  ok   %-66s\n' "template checked: ${f##*/}"
}
tpl e2e-critical-journey.spec.ts "from '@playwright/test'" "test(" "AC-1" "@critical" "expect("
tpl visual.spec.ts "toHaveScreenshot(" "maxDiffPixelRatio" "threshold" "mask:" "animations: 'disabled'" "--update-snapshots"
tpl a11y.spec.ts "import AxeBuilder from '@axe-core/playwright'" ".withTags(" "wcag2a" "wcag2aa" "wcag21aa" "wcag22aa" "violations).toEqual([])"
tpl responsive.spec.ts "320" "768" "1280" "scrollWidth" "clientWidth" "setViewportSize"
tpl playwright.config.ts "defineConfig" "devices['Desktop Safari']" "channel: 'msedge'" "retries"
tpl load.k6.js "from 'k6/http'" "thresholds" "http_req_duration" "p(95)<" "http_req_failed" "rate<" "smoke" "load" "stress" "soak" "__ENV.SCENARIO"
tpl maestro-flow.yaml "appId:" "---" "launchApp" "tapOn" "assertVisible" "AC-1"
tpl smoke.sh "curl" "HEALTH_PATH" "SMOKE_PATH" "set -euo pipefail"
tpl exploratory-charter.md "charter" "areas" "risks" "timebox" "Notes" "Explore It!" "Bach"
tpl flaky-test-policy.md "quarantine" "owner" "expir" "rerun"
bash -n "$T/smoke.sh" && { PASS=$((PASS+1)); echo "  ok   smoke.sh parses (bash -n)"; } || { FAIL=$((FAIL+1)); echo "  FAIL smoke.sh syntax"; }
if command -v node >/dev/null 2>&1; then
  node --check "$T/load.k6.js" >$OUT/node.out 2>&1 && { PASS=$((PASS+1)); echo "  ok   load.k6.js parses (node --check)"; } \
    || { FAIL=$((FAIL+1)); echo "  FAIL load.k6.js syntax"; cat $OUT/node.out; }
else echo "  skip node --check (node not installed)"; fi
python3 - "$T/maestro-flow.yaml" <<'EOF' && { PASS=$((PASS+1)); echo "  ok   maestro-flow.yaml has a header and a command list"; } || { FAIL=$((FAIL+1)); echo "  FAIL maestro-flow.yaml shape"; }
import sys
head, _, body = open(sys.argv[1]).read().partition("\n---\n")
assert "appId:" in head and body.lstrip().startswith("- ")
EOF

# ================================================================== fixture
expect 1 "examples/qa fixture: partial coverage detected" trace "$ROOT/examples/qa/spec.md" --tests "$ROOT/examples/qa/tests"
has "uncovered: AC-3, AC-4, AC-5"
nothas "fixtures.py"
has "covered   AC-2"

echo
echo "testplan: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
