---
name: bug-fix
description: >
  Use when something is broken and the change is a fix, not new work — a crash, a
  wrong return value, a regression, a user-reported defect, a test that started
  failing. Enforces repro-first: reproduce before reading code, commit the
  reproduction as a failing test before touching the implementation, fix only the
  narrowest thing that makes it pass, and grep for sibling instances of the same
  bug class elsewhere in the codebase. Use PROACTIVELY before editing code in
  response to a bug report, a crash, or a failing test.
---

# Bug fix

An unreproduced bug is a guess. The cheapest, most scale-independent practice found
across the whole research pass is the fuzz-finding-to-regression-test loop that
OSS-Fuzz itself prescribes: commit the crash/bug input as a permanent test, and make
replaying it a normal part of the suite — no special infrastructure required, a bug
reporter's repro works exactly like a fuzzer's crash file
(`google/oss-fuzz@2cc3fa4:docs/advanced-topics/ideal_integration.md`, concretely
realised in `sqlite/sqlite@86876d2:test/fuzzcheck.c`'s in-tree corpus). This skill is
that loop, applied to any bug, not just fuzzer-found ones.

## Trigger

**Fire when:** a crash, a wrong output, a regression, or a failing test needs to be
fixed. The change is corrective, not additive.

**Do not fire when:** you are writing new behavior (`feature-planning` instead), or
the cause is already root-caused by a completed `root-cause-analysis` record — then
you are just doing step 2 onward, with the mechanism already known.

## Rules

1. Reproduce before reading the implementation. Reading code first means the fix is
   shaped by a theory, not by evidence.
   *Enforced by:* convention

2. Commit the reproduction as a **failing** test before writing any fix, and see it
   fail for the right reason — assert on the specific wrong output, not just "it
   throws".
   *Enforced by:* `git stash && <single-test-runner> <new-test-path>` must exit
   non-zero with the fix stashed away; `git stash pop` restores it. See Verify.

3. Only then find the cause. Fix the narrowest change that makes the failing test
   pass — one root cause, one diff.
   *Enforced by:* `python3 scripts/bloat_check.py` — flags a diff that grew past the
   fix (new files, new abstractions, unrelated hunks)

4. Do not fix adjacent things you noticed while in there. A second defect gets its
   own reproduction, its own failing test, and its own diff — bundling it here hides
   both changes from review.
   *Enforced by:* review

5. Ask what class of bug this is, and grep the codebase for the same pattern. A
   sibling of this bug is still live until it is checked, not until this one is
   fixed.
   *Enforced by:* `grep -rn "<the specific pattern>" --include="*.<ext>" .`

6. The test stays forever. Never delete it, skip it, or mark it `.only`/`.skip` —
   it is the actual deliverable of the fix, not scratch work that outlived its use.
   *Enforced by:* `python3 scripts/bloat_check.py --only focused-tests`

## Verify

```bash
# 1. reproduce BEFORE reading code — capture the exact command, not a description
curl -s localhost:3000/orders/999           # or the failing test's node id, or the crash repro
#   ~seconds

# 2. commit the reproduction as a FAILING test, and watch it fail for the right reason
git stash                                    # hide any fix already in progress
pytest tests/test_bug.py::test_repro -x      # or: npx jest test_bug -t "..." / go test ./... -run TestBug
echo "expect non-zero: $?"
git stash pop
#   ~seconds to a minute, one test only — never the whole suite here

# 3. after the fix: the same test now passes, and the diff stayed narrow
pytest tests/test_bug.py::test_repro -x      # now exits 0
python3 scripts/bloat_check.py               # diff-scoped: scope creep, focused/skipped tests
#   ~1-3s, diff-scoped

# 4. sibling check — same class of bug elsewhere in the codebase
grep -rn "<pattern that caused this>" --include="*.ts" .

# 5. if the cause isn't obvious from inspection, bisect for it
git bisect start
git bisect bad HEAD
git bisect good <last-known-good-sha>
git bisect run pytest tests/test_bug.py::test_repro -x
git bisect reset
```

## Failure modes

This skill rejects:

- **A fix with no accompanying test.** Nothing prevents the bug from returning
  silently.
- **A test added after the fix**, or never run red — it cannot prove it would have
  caught the bug, only that it passes now, which any test does.
- **A test that doesn't actually fail** before the fix: asserts nothing, catches the
  wrong exception type, or checks a symptom loose enough that the old code also
  satisfies it.
- **An unrelated cleanup bundled into the bug-fix diff** — `bloat_check.py` flags the
  growth; review decides if it's the fix or a second change wearing the fix's diff.
- **Deleting or skipping the regression test later** ("it's flaky", "not needed
  anymore") — `bloat_check.py --only focused-tests` catches `.only`/`.skip` directly;
  deletion itself shows up as a test-file removal in the next diff review.
- **Fixing the first plausible cause found**, without checking whether the same
  pattern exists elsewhere — a sibling bug shipped the same week as this fix is the
  single most demoralizing outcome of a bug-fix pass.

**Honest limitations:**
- Nothing here proves the test asserts the *right* thing — only that it existed,
  failed before the fix, and passes after. A weak assertion (loose equality, no
  error-message check) passes trivially; that is `bloat_check.py`'s assertionless-test
  check catching the extreme case, and human review catching the rest.
- Rule 1 is honor-system: nothing mechanically proves code wasn't read first. The
  practical enforcement is rule 2 — if there is no failing test that predates the
  fix, the order cannot have been followed either.
- When the bug is genuinely mysterious (intermittent, cause not obvious after one
  reproduction attempt), stop here and use `root-cause-analysis` instead — it adds
  timeline reconstruction and hypothesis discipline that this skill deliberately
  keeps light for the common case.

## Scale

`solo` and up, and the value does not really scale with team size — a committed
regression test is exactly as valuable to a solo maintainer as to a 200-person org,
which is why the research names it the single cheapest, most scale-independent
practice found in the whole study. What *does* scale with team size is rule 5 (the
sibling grep): at `org` size the same bug class often exists in five services nobody
has looked at yet.

## Sources
- The fuzz-finding-to-regression-test loop ("commit the crash input as a corpus
  entry, replay it as a normal test-suite target"), and its generalization to any bug
  repro: `google/oss-fuzz@2cc3fa4:docs/advanced-topics/ideal_integration.md`,
  concretely realised in `sqlite/sqlite@86876d2:test/fuzzcheck.c` — both cited in
  full in `research/35-findings-security-reliability.md`.
- "A failing test, a tiny repo, or a self-contained code snippet" as the required
  shape of a bug reproduction: `prisma/orm:bug_report.yml`, one of 12/16 repos
  surveyed that require minimal reproduction before a bug report is actioned —
  `research/37-findings-review-governance.md`.
- `scripts/bloat_check.py` and its focused-tests / assertionless-test checks are this
  plugin's own tool, reused here rather than reimplemented: `skills/minimal-diff/SKILL.md`,
  `SOURCE: original`.
- Rule ordering (reproduce, commit a failing test, narrowest fix, sibling grep,
  permanent test) is this skill's own synthesis of the above sources: `SOURCE: original`.
