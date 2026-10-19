#!/usr/bin/env bash
# Regression suite for prose_check.py. Every rule has a planted violation, and every clean
# fixture must produce 0 findings: a prose linter that flags good writing gets ignored.
# Fixtures are synthetic (evals/fixtures/prose/). Run: bash tests/test_prose_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PC="$ROOT/scripts/prose_check.py"
FX="$ROOT/evals/fixtures/prose"
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; sed 's/^/       /' "$OUT/pc.out"; }
run() { python3 "$PC" "$@" >"$OUT/pc.out" 2>&1; echo $? >"$OUT/pc.exit"; }

detects() { # detects <rule> <fixture> [prose_check args...]
  local rule="$1" fx="$2"; shift 2
  run "$@" "$FX/bad/$fx"
  grep -q "\[$rule\]" "$OUT/pc.out" && ok "$rule: detected in bad/$fx" || bad "$rule: NOT detected in bad/$fx"
}
clean() { # clean <fixture> [prose_check args...]
  local fx="$1"; shift
  run "$@" "$FX/good/$fx"
  grep -q "prose_check: 0 finding" "$OUT/pc.out" && ok "clean: good/$fx has 0 findings" || bad "false positive in good/$fx"
}

echo "--- detection: one planted violation per rule"
detects body-budget                pr-over-budget.md      --kind pr --diff-lines 40
detects long-paragraph             long-paragraph.md      --kind doc
detects claim-without-evidence     claim-no-evidence.md   --kind pr --diff-lines 40
detects claim-without-evidence     claim-phrasing.md      --kind pr --diff-lines 40
detects filler-phrase              filler.md              --kind pr --diff-lines 40
detects self-ticked-box            ticked-box.md          --kind pr --diff-lines 40
detects history-section            history.md             --kind pr --diff-lines 40
detects heading-overload           heading-overload.md    --kind pr --diff-lines 40
detects long-bullet                long-bullet.md         --kind pr --diff-lines 40
detects missing-issue-link         missing-issue-link.md  --kind pr --diff-lines 40
detects review-comment-no-severity review-no-severity.md  --kind review-comment
detects review-comment-multi-ask   review-multi-ask.md    --kind review-comment
detects review-comment-no-scenario review-no-scenario.md  --kind review-comment
detects reply-fixed-no-sha         reply-no-sha.md        --kind reply
detects summary-first              doc-heading-wall.md    --kind doc
detects summary-first              doc-long-opening.md    --kind doc
detects code-comment-narration     code-comment-narration.txt --kind code-comment

run --kind code-comment "$FX/bad/code-comment-narration.txt"
[ "$(grep -c "\[code-comment-narration\]" "$OUT/pc.out")" = 4 ] && ok "code-comment-narration: all 4 mechanics lines flagged" \
  || bad "code-comment-narration: expected 4 findings"

echo "--- claim phrasing: each form is a claim, the ordinary verb is not"
python3 - "$ROOT/scripts" <<'PY' >"$OUT/pc.out" 2>&1 && ok "CLAIM_RX: claim forms flagged, ordinary verbs not" || bad "CLAIM_RX table"
import sys
sys.path.insert(0, sys.argv[1])
from prose_check import check_text
claims = ["The tests passed.", "CI passed.", "The build passes.", "Verified the retry.",
          "I verified that it retries.", "I tested the export.", "We've tested it.",
          "Tested locally.", "Tested against the sandbox.", "Confirmed that it retries.",
          "Confirmed it works.", "Confirmed locally.", "100% coverage on the parser.",
          "All tests pass."]
plain = ["Values are passed by reference.", "The token is confirmed by email.",
         "The signature is verified by the gateway.", "A tested pattern is the opt-in.",
         "The flag is passed to the worker.", "Each check is tested by the CI job."]
rule = "claim-without-evidence"
missed = [c for c in claims if not any(f["rule"] == rule for f in check_text(c + "\n", "doc"))]
wrong = [c for c in plain if any(f["rule"] == rule for f in check_text(c + "\n", "doc"))]
assert not missed and not wrong, (missed, wrong)
PY

echo "--- the combined slop body trips most rules at once"
run --kind pr --diff-lines 40 "$FX/bad/pr-slop.md"
for r in body-budget missing-issue-link claim-without-evidence filler-phrase history-section \
         long-paragraph long-bullet self-ticked-box heading-overload; do
  grep -q "\[$r\]" "$OUT/pc.out" && ok "pr-slop: $r" || bad "pr-slop: $r missing"
done
grep -q "pr-slop.md:15: \[self-ticked-box\]" "$OUT/pc.out" && ok "findings carry the right line number" \
  || bad "line number for the first ticked box"

echo "--- no false positives on clean input"
clean pr-small.md             --kind pr --diff-lines 40
clean pr-template.md          --kind pr --diff-lines 40
clean pr-verified.md          --kind pr --diff-lines 40
clean review-must.md          --kind review-comment
clean review-nit.md           --kind review-comment
clean review-ask.md           --kind review-comment
clean review-conventional.md  --kind review-comment
clean reply-done.md           --kind reply
clean reply-kept.md           --kind reply
clean doc.md                  --kind doc
clean commit.txt              --kind commit
clean chat.md                 --kind chat
clean code-comment.txt        --kind code-comment
clean code-comment-why.txt    --kind code-comment
clean ordinary-verbs.md       --kind doc
clean code-blocks-verified.md --kind doc
run --kind doc "$ROOT/docs/WRITING.md"
grep -q "prose_check: 0 finding" "$OUT/pc.out" && ok "clean: docs/WRITING.md passes its own check" \
  || bad "docs/WRITING.md has findings"

echo "--- thresholds scale with the diff"
run --kind pr --diff-lines 400 "$FX/bad/pr-over-budget.md"
grep -q "\[body-budget\]" "$OUT/pc.out" && bad "body-budget fired for a 400-line diff" \
  || ok "body-budget: 853 chars is within budget for a 400-line diff"
run --kind pr --diff-lines 250 "$FX/bad/history.md"
grep -q "\[history-section\]" "$OUT/pc.out" && bad "history-section fired for a 250-line diff" \
  || ok "history-section: allowed when the diff is 200+ lines"
run --kind pr "$FX/bad/pr-over-budget.md"
grep -q "body-budget skipped" "$OUT/pc.out" && ok "pr without --diff-lines says body-budget was skipped" \
  || bad "missing skip notice without --diff-lines"

echo "--- exit codes"
run --kind pr --diff-lines 40 "$FX/bad/pr-slop.md"
[ "$(cat "$OUT/pc.exit")" = 0 ] && ok "default: exit 0 even with findings" || bad "default exit was $(cat "$OUT/pc.exit")"
run --kind pr --diff-lines 40 --strict "$FX/bad/pr-slop.md"
[ "$(cat "$OUT/pc.exit")" = 1 ] && ok "--strict: exit 1 with findings" || bad "--strict exit was $(cat "$OUT/pc.exit")"
run --kind reply --strict "$FX/good/reply-done.md"
[ "$(cat "$OUT/pc.exit")" = 0 ] && ok "--strict: exit 0 on clean input" || bad "--strict clean exit was $(cat "$OUT/pc.exit")"
run --kind doc "$FX/good/no-such-file.md"
[ "$(cat "$OUT/pc.exit")" = 2 ] && ok "unreadable input: exit 2" || bad "unreadable exit was $(cat "$OUT/pc.exit")"
python3 "$PC" --kind reply - <"$FX/bad/reply-no-sha.md" >"$OUT/pc.out" 2>&1
grep -q "^-:1: \[reply-fixed-no-sha\]" "$OUT/pc.out" && ok "stdin '-' is read and named '-'" || bad "stdin input"

echo "--- check_text() contract"
python3 - "$ROOT/scripts" <<'PY' >"$OUT/pc.out" 2>&1 && ok "check_text returns {rule, line, message} dicts" || bad "check_text contract"
import sys
sys.path.insert(0, sys.argv[1])
from prose_check import check_text
found = check_text("Fixed, thanks.\n", "reply")
assert found == [{"rule": "reply-fixed-no-sha", "line": 1, "message": found[0]["message"]}], found
assert check_text("Done in 3f9c2ab: dropped the retry.\n", kind="reply") == []
assert check_text("closes #1\n\n- Small fix.\n", "pr", diff_lines=5) == []
try:
    check_text("x", "tweet")
    raise SystemExit("unknown kind accepted")
except ValueError:
    pass
PY

echo
echo "prose_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
