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

| field | value |
|---|---|
| feature | tagging |

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
has "^\| TC-1-1 \| tagging/AC-1 \| e2e \| equivalence partition \(valid\)"
has "\| TC-1-[0-9]+ \| tagging/AC-1 \| unit \| boundary value \| value = 11 \| rejected.*max\+1"
has "\| tagging/AC-1 \| unit \| boundary value \| value = 10 \| accepted \(max\)"
has "\| tagging/AC-4 \| unit \| boundary value \| value = 0 \| rejected"
has "\| tagging/AC-4 \| unit \| boundary value \| value = 281 \| rejected"
has "\| tagging/AC-2 \| integration \| negative / authz \|"
has "\| tagging/AC-3 \| integration \| state transition \(illegal\) \|"
has "\| tagging/AC-1 \| [a-z]+ \| equivalence partition \(invalid\) \|"
has "\| TC-web.reflow-320-1 \| web.reflow-320 \| e2e \|"
has "\| TC-api.p95-budget-1 \| api.p95-budget \| load \|"
has "\| TC-a11y.wcag22-aa-1 \| a11y.wcag22-aa \| a11y \|"
has "^\| case id \| AC id \| level \| technique \| input / precondition \| expected \| automated\? \| owner \|"
has "4 acceptance criteria, 3 implicit requirements"
has "Tag every test with its namespaced id \\(\`tagging/AC-1\`\\)"
nothas "\| tagging/AC-2 \| unit \| boundary value \| value ="     # no numbers in AC-2: no boundary rows
nothas "\| tagging/AC-4 \| integration \| state transition"       # no state words in AC-4
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

# the canonical plan_feature shape: links are metadata, not wording to derive cases from
cat > canon.md <<'EOF'
# Spec
## 2b. Acceptance criteria
AC-1: Only the album owner can delete a tag. (R2, S1)
AC-2: A comment holds at most 280 characters. (R3)
EOF
expect 0 "new: canonical AC lines with (R, S) links parse" new canon.md
has "2 acceptance criteria"
has "\| canon/AC-2 \| unit \| boundary value \| value = 281 \|"
nothas "\(R2, S1\)"                                        # links stripped from case text
nothas "value = 2 \|"                                       # 'R2' is not a boundary number
python3 -c "
import sys; sys.path.insert(0, '$ROOT/scripts')
from _md import parse_criteria
c = parse_criteria(open('canon.md').read())
assert [x['links'] for x in c] == [['R2', 'S1'], ['R3']], c
" && { PASS=$((PASS+1)); echo "  ok   parse_criteria returns the R/S links"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL parse_criteria links"; }

# a bare --out files the plan beside the spec: <root>/specs/<feature>/testplan.md
mkdir -p feat/work/billing && cp canon.md feat/work/billing/spec.md
(cd feat && git init -q && "$TX" testplan new work/billing/spec.md --out >$OUT/tp.out 2>&1)
[ -f feat/docs/engineering/specs/billing/testplan.md ] && { PASS=$((PASS+1)); echo "  ok   bare --out writes docs/engineering/specs/billing/testplan.md"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL bare --out did not write beside the spec"; cat $OUT/tp.out; }
[ ! -e feat/docs/engineering/testplans ] && { PASS=$((PASS+1)); echo "  ok   bare --out no longer creates testplans/"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL bare --out still wrote testplans/"; }
printf '{"schema": 1, "root": "eng"}\n' > feat/.100x.json
(cd feat && "$TX" testplan new work/billing/spec.md --out >$OUT/tp.out 2>&1)
[ -f feat/eng/specs/billing/testplan.md ] && { PASS=$((PASS+1)); echo "  ok   bare --out follows .100x.json"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL bare --out ignored .100x.json"; cat $OUT/tp.out; }
# a plan at the legacy <root>/testplans/<feature>.md is found, not silently duplicated
mkdir -p feat/eng/testplans && echo "# old plan" > feat/eng/testplans/legacy.md
cp canon.md feat/work/legacy.md
(cd feat && "$TX" testplan new work/legacy.md --out >$OUT/tp.out 2>&1); rc=$?
[ "$rc" -eq 2 ] && [ ! -e feat/eng/specs/legacy/testplan.md ] && { PASS=$((PASS+1)); echo "  ok   legacy testplans/<feature>.md: bare --out refuses to duplicate it"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL legacy plan duplicated (exit $rc)"; cat $OUT/tp.out; }
has "note: a test plan for legacy exists at the legacy location eng/testplans/legacy.md"
has "git mv eng/testplans/legacy.md eng/specs/legacy/testplan.md"
(cd feat && "$TX" testplan new work/legacy.md --out --force >$OUT/tp.out 2>&1)
[ -f feat/eng/specs/legacy/testplan.md ] && grep -q "old plan" feat/eng/testplans/legacy.md && { PASS=$((PASS+1)); echo "  ok   legacy: --force writes the new location, leaves the old file"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL legacy --force"; cat $OUT/tp.out; }

# ===================================================================== trace
mkdir -p t/e2e t/api src t/.maestro t/node_modules/pkg
cat > t/e2e/tag.spec.ts <<'EOF'
import { test, expect } from '@playwright/test';
test('tagging/AC-1 tags ten people', { tag: '@critical' }, async ({ page }) => {
  await expect(page.getByRole('list')).toBeVisible();
});
// test('tagging/AC-3 publishing a draft', async ({ page }) => {
//   await expect(page.getByText('Published')).toBeVisible();
// });
/*
test('tagging/AC-3 block-commented test', async () => {
  expect(1).toBe(1);
});
*/
test.skip('tagging/AC-4 comment length', async () => { expect(1).toBe(1); });
EOF
cat > t/api/test_delete.py <<'EOF'
# Covers tagging/AC-2 (owner-only delete)
def test_non_owner_cannot_delete(client):
    assert client.delete("/tags/1").status_code == 403
EOF
printf '// tagging/AC-3 tagging/AC-4 mentioned in a helper, not a test\nexport const X = 1;\n' > t/e2e/helpers.ts
printf '# tagging/AC-3\nCOMMENT_MAX = 280  # tagging/AC-4\n' > t/api/fixtures.py
printf 'tagging/AC-3 described in a README\n' > t/README.md
printf '// tagging/AC-3 in vendored code\ntest("tagging/AC-3", () => {});\n' > t/node_modules/pkg/x.test.js

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
it('publishes a draft once confirmed @tagging/AC-3', () => { expect(true).toBe(true); });
EOF
cat > t/.maestro/comment.yaml <<'EOF'
appId: com.example.app
tags:
  - tagging/AC-4
---
- launchApp
EOF
cat > t/api/limits_test.go <<'EOF'
package api
// tagging/AC-99 references an id the spec never defined
func TestCommentLimit(t *testing.T) {}
EOF
expect 0 "trace: all ACs covered exits 0 (vitest @tag + maestro tags)" trace spec.md --tests t
has "4/4 ACs covered"
has "publish.test.tsx:2"
has "comment.yaml:3"
has "WARN tag for an AC the spec does not define: .*tagging/AC-99"

mkdir -p t2
printf "test('tagging/AC-1 x', () => { expect(1).toBe(1) })\n" > t2/a.test.js
printf "test('tagging/AC-2 x', () => { expect(1).toBe(1) })\n" > t2/b.test.js
expect 1 "trace: comma-separated dirs combine (AC-3, AC-4 still missing)" trace spec.md --tests t2,t/api
has "covered   AC-1"
has "covered   AC-2"
expect 2 "trace: nonexistent --tests dir exits 2, never a silent pass" trace spec.md --tests does-not-exist

# decision (a): only <feature>/AC-<n> tags for THIS spec's feature count
mkdir -p t3
cat > t3/ns.test.ts <<'EOF'
test('AC-1 bare tag', () => { expect(1).toBe(1); });
test('billing/AC-2 another feature', () => { expect(1).toBe(1); });
test('tagging/AC-3 this feature', () => { expect(1).toBe(1); });
EOF
expect 1 "trace: bare and other-feature tags do not count" trace spec.md --tests t3
has "UNCOVERED AC-1"
has "UNCOVERED AC-2"
has "covered   AC-3"
has "HINT 1 bare AC-<n> tag\(s\) not counted \(first: t3/ns.test.ts:1 AC-1\)"
has "tag tests .tagging/AC-<n>."
has "1 tag\(s\) for other features ignored"
expect 1 "trace --feature billing: only billing's AC-2 counts" trace spec.md --tests t3 --feature billing
has "covered   AC-2"
has "UNCOVERED AC-3"

# a skipped group marks every test inside it, however deep (Code P7)
mkdir -p t4
cat > t4/group.spec.ts <<'EOF'
describe.skip('tagging', () => {
  beforeEach(() => { setup({ a: 1 }); });
  describe('nested', () => {
    it('tagging/AC-1 deep inside a skipped group', () => {
      expect(1).toBe(1);
    });
  });
});
xdescribe('old', () => {
  it('tagging/AC-2 inside xdescribe', () => {});
});
context.skip('ctx', () => {
  it('tagging/AC-3 inside context.skip', () => {});
});
describe('live group', () => {
  it('tagging/AC-4 runs', () => { expect('}').toBe('}'); });
});
EOF
cat > t4/test_group.py <<'EOF'
import pytest


@pytest.mark.skip(reason="flaky")
class TestTagging:
    def test_one(self):
        assert True  # tagging/AC-1

    def test_two(self):
        assert True  # tagging/AC-2


def test_live():
    assert True  # tagging/AC-3
EOF
expect 1 "trace: tags inside skipped groups do not count" trace spec.md --tests t4
has "UNCOVERED AC-1"
has "UNCOVERED AC-2"
has "group.spec.ts:4 \(skipped test"
has "group.spec.ts:10 \(skipped test"
has "group.spec.ts:13 \(skipped test"
has "test_group.py:10 \(skipped test"
has "covered   AC-3"
has "test_group.py:14"
has "covered   AC-4"
has "group.spec.ts:16"

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
tpl e2e-critical-journey.spec.ts "from '@playwright/test'" "test(" "<feature>/AC-1" "@critical" "expect("
tpl visual.spec.ts "toHaveScreenshot(" "maxDiffPixelRatio" "threshold" "mask:" "animations: 'disabled'" "--update-snapshots"
tpl a11y.spec.ts "import AxeBuilder from '@axe-core/playwright'" ".withTags(" "wcag2a" "wcag2aa" "wcag21aa" "wcag22aa" "violations).toEqual([])"
tpl responsive.spec.ts "320" "768" "1280" "scrollWidth" "clientWidth" "setViewportSize"
tpl playwright.config.ts "defineConfig" "devices['Desktop Safari']" "channel: 'msedge'" "retries"
tpl load.k6.js "from 'k6/http'" "thresholds" "http_req_duration" "p(95)<" "http_req_failed" "rate<" "smoke" "load" "stress" "soak" "__ENV.SCENARIO"
tpl maestro-flow.yaml "appId:" "---" "launchApp" "tapOn" "assertVisible" "<feature>/AC-1"
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

# ============================================================ implicit levels
# Real baseline ids, as plan_feature writes them: the `web-ui.` prefix survives, and the
# level comes from the requirement, never from the evidence column (which names axe,
# k6, web-vitals and screenshots on purpose in the fixture).
QA="$ROOT/examples/qa/spec.md"
expect 0 "new: real baseline ids generate cases" new "$QA"
has "\| TC-web-ui.reflow-320-1 \| web-ui.reflow-320 \| e2e \| non-functional \| responsive"
has "\| web-ui.contrast-and-targets \| a11y \| non-functional \| axe scan"
has "\| web-ui.analytics-consent \| e2e \|"
has "\| api.health-graceful-shutdown \| integration \|"
has "\| api.boundary-validation \| integration \|"
has "\| all.tests-in-same-change \| review \| .* \| no \| qa-engineer \|"
has "\| api.authz-every-endpoint \| integration \| non-functional \| negative authz"
has "\| api.p95-budget \| load \|"
nothas "\| ui\.reflow-320 \|"                                         # prefix not truncated
nothas "\| (web-ui.analytics-consent|api.health-graceful-shutdown|api.boundary-validation|all.tests-in-same-change) \| (load|a11y|visual) \|"
nothas "\| e2e \| non-functional \| field/lab web-vitals budget check \(see the web-vitals skill\) \| every input"
nothas "TC-api.rate-limit-1"                                         # n/a(...)
nothas "TC-web-ui.seo-meta-1"                                        # waived(...)
nothas "TC-ask\."                                                     # questions, not behaviour
has "No case for 3 implicit-requirement row\(s\) with nothing to test: api.rate-limit \(n/a\), web-ui.seo-meta \(waived\), ask.data-residency \(a question\)"
has "8 implicit requirements"
nothas "k6 run shows|axe scan of the status page|visual snapshots updated"   # evidence is not the expected outcome
python3 - "$ROOT" >$OUT/tp.out 2>&1 <<'EOF'
import json, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import testplan as tp
items = json.load(open(sys.argv[1] + "/scripts/data/baseline.json"))["items"]
missing = [i["id"] for i in items if i["id"] not in tp.LEVEL_BY_ID and not i.get("level")
           and not i["id"].startswith("ask.")]
assert not missing, f"baseline ids with no test level: {missing}"
assert set(tp.LEVEL_BY_ID.values()) <= set(tp.NFR_HOW), set(tp.LEVEL_BY_ID.values()) - set(tp.NFR_HOW)
assert tp.NFR_ID.search("| `web-ui.reflow-320` |").group(1) == "web-ui.reflow-320"
assert tp.NFR_ID.search("data-pipeline.pii-lineage").group(1) == "data-pipeline.pii-lineage"
assert tp.NFR_ID.search("v1.2") is None or tp.NFR_ID.search("v1.2").group(1) != "1.2"
# a `level` hint on a baseline item wins over the built-in table
tp.BASELINE_BY_ID["web-ui.seo-meta"] = {"level": "static"}
assert tp.nfr_level("web-ui.seo-meta", "") == "static"
# keyword fallback for a team's own ids: whole words, id before text
assert tp.nfr_level("team.consent-banner", "trackers load only after consent") is None
assert tp.nfr_level("team.p95-checkout", "") == "load"
assert tp.nfr_level("team.reflow-check", "") == "responsive"
assert tp.skip_reason("ask.slo-numbers", "ASSUMED(99.9%)") == "a question"
assert tp.skip_reason("api.x", "N/A(internal)") == "n/a"
assert tp.skip_reason("api.x", "covered") is None
assert tp.TIERS == json.load(open(sys.argv[1] + "/scripts/data/scale_tiers.json"))["_order"]
EOF
[ $? -eq 0 ] && { PASS=$((PASS+1)); echo "  ok   every baseline id has a level; id regex keeps hyphenated prefixes; tiers from scale_tiers.json"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL level table / id regex"; sed 's/^/       /' $OUT/tp.out; }

# ================================================================== fixture
expect 1 "examples/qa fixture: partial coverage detected" trace "$ROOT/examples/qa/spec.md" --tests "$ROOT/examples/qa/tests"
has "uncovered: AC-3, AC-4, AC-5"
nothas "fixtures.py"
has "covered   AC-2"
has "HINT 1 bare AC-<n> tag.*publish.spec.ts:4 AC-3"

echo
echo "testplan: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
