---
name: test-design
description: >
  Use when choosing WHICH test cases to write, for new code or a diff that adds
  tests — equivalence partitioning and boundary values, pairwise coverage for
  combinatorial booleans, illegal state transitions, test-double choice (stub vs
  spy vs mock vs fake, and not mocking what you do not own), test naming as
  specification, one logical assertion per test, determinism, and where
  property-based testing beats hand-written examples. Not for whether a test CAN
  fail at all (assertionless/focused-test detection lives in minimal-diff) and
  not for which commands a language's suite should run (python-verification,
  typescript-verification, go-verification). Use PROACTIVELY before writing any
  test, and when reviewing a diff that adds them.
---

# Test design

`minimal-diff` catches whether a test can fail. `python-verification` and its
siblings catch whether the suite runs and gates CI. Neither says anything about
whether the cases chosen would catch a real bug — and across 72 JS/TS and 50
Python production repos, a patch-coverage gate exists in exactly 1 of 72
(`TriliumNext/Trilium`), mutation testing exists in 0 of 72 and 0 of 50, and
property-based testing is confirmed in 2 of 50 (`research/30`, `research/31`).
A green suite and a coverage number are evidence the tests run, not evidence
they would catch anything. This skill is the missing layer: how to pick cases.

## Trigger

**Fire when:** writing tests for new behavior; reviewing a diff that adds tests;
deciding how many cases a function needs; a test suite passes but a bug still
shipped.

**Do not fire when:** the question is whether a test asserts anything at all
(`minimal-diff` owns assertion-free and `.only`/`.skip` detection) or which
runner/lint/type-checker a language project should use (the `*-verification`
skills). Changing code that currently has zero tests is `legacy-change` first —
come back here once a characterization test exists to extend from.

## Rules

1. **Partition the input, then test the boundaries.** For any bounded or sized
   input, the cases are min-1, min, min+1, typical, max-1, max, max+1. The two
   missing more often than any others: **max+1** (the off-by-one nobody wrote)
   and **empty** (the case that isn't "small", it's zero elements). A boundary
   bug lives at the boundary, never in the middle of a partition.
   *Enforced by:* `python3 scripts/test_design_check.py --only single-value`
   (advisory, heuristic — flags a lone test exercising one numeric value with no
   table/parametrize sibling in the file; see Failure modes)

2. **Use pairwise coverage for combinatorial booleans, and know the arithmetic.**
   4 independent booleans is 2⁴ = 16 combinations to fully cover; pairwise
   (every 2-way interaction covered at least once) needs as few as 5-9 cases,
   because most real bugs are triggered by an interaction of 2 flags, not all N
   at once. 6 booleans: 64 exhaustive vs. ~10 pairwise. This is not "fewer tests
   is better" — it is "the combinations most likely to hide a bug, for a
   fraction of the exhaustive cost."
   *Enforced by:* review

3. **For anything with states, enumerate the legal transitions — then test the
   illegal ones.** Draw or list the state machine (even 4-5 states is enough to
   need this). An unhandled illegal transition — cancel-after-ship, refund
   before charge, delete during upload — is the classic production bug, because
   the legal path is the one everyone tests.
   *Enforced by:* review

4. **Size the pyramid to where the risk actually is, not to a shape.** Unit
   tests cover logic with no boundary crossing; integration tests cover the
   boundary itself (DB, queue, external call); end-to-end covers the one or two
   flows that must never break. A service-heavy "test diamond" — thin unit
   layer, thick integration layer — is correct, not heretical, when most of a
   codebase's real logic is orchestration across boundaries. Justify the shape
   from where bugs actually occur, not a default 70/20/10 ratio.
   *Enforced by:* review

5. **Know which double you're reaching for.** A **stub** returns canned data. A
   **spy** records calls for later inspection. A **mock** asserts *how* it was
   called (arguments, call count, order) — which makes the test couple to the
   implementation, not the behavior: refactor the call shape with the behavior
   unchanged, and a mock-heavy test fails anyway. A **fake** is a working
   lightweight implementation (in-memory DB, in-memory queue) — prefer it when
   the interaction itself isn't what you're testing.
   *Enforced by:* review

6. **Do not mock what you do not own.** Mocking a third-party module's
   internals (`stripe.Charge.create`, `boto3.client`) couples the test to that
   library's implementation, not its contract — a minor version bump can pass
   every mocked test and break production. Put a narrow interface (a port) of
   your own in front of the dependency, and fake *that* instead.
   *Enforced by:* `python3 scripts/test_design_check.py --only mock-thirdparty`
   (advisory — heuristic on module path/specifier, see Failure modes)

7. **Name the test as a sentence describing the behaviour, not the function.**
   `test_handles_empty_input`, `it('returns the cached value on a second call')`,
   `Test_UnitParseHeader` (k3s's own generated-test convention). A reader should
   learn the contract from `grep -o 'def test_.*' tests/*.py` alone, without
   opening a single file. `test_1`, `testFoo`, `it('works')` describe nothing.
   *Enforced by:* `python3 scripts/test_design_check.py --only test-name`
   (blocking — see Failure modes for what it deliberately does not flag)

8. **One logical assertion per test, arranged as Arrange/Act/Assert.** A test
   with four unrelated assertions and a `pytest`/`jest` runner that stops at the
   first failure means the other three never ran — a fix to assertion 1 can
   still be wrong in assertions 2-4, and nothing says so until the next run.
   Split by behaviour, not by convenience.
   *Enforced by:* `python3 scripts/test_design_check.py --only assert-count`
   (advisory, default threshold 4 — `--max-asserts N` to change it)

9. **Determinism: no sleeps, no real clock, no shared mutable fixture, no order
   dependence.** Each has a name because each is a distinct, recurring failure:
   a `time.sleep`/`setTimeout` delay is *flaky-under-load*; a bare
   `datetime.now()`/`Date.now()` is *time-dependent-flake*; a fixture object
   reused and mutated across tests is *fixture-bleed*; a test that only passes
   after another one ran first is *order-dependence*. `apache/airflow`'s own
   contributor guide states the sleep rule directly: "you should mock sleep
   calls in tests or set the sleep time to 0."
   *Enforced by:* `python3 scripts/test_design_check.py --only sleep` (blocking)
   and `--only realtime` (advisory — clock use with no freeze/injection)

10. **Do not test generated code, framework behaviour, a private method via
    reflection, or a getter.** Each has zero marginal information: generated
    code is tested by testing its generator once; framework behaviour is the
    framework's test suite's job; a private method is only reachable through a
    public one, so test that; a getter with no logic can only fail if the
    language itself is broken. Every test has a carrying cost — maintenance,
    runtime, review — spend it on cases that can actually be wrong.
    *Enforced by:* review

11. **Reach for property-based testing on parsers, serializers, and anything
    with an invariant (idempotency, round-trip, ordering).** A hand-written
    example proves one input works; a property (`parse(serialize(x)) == x`)
    proves it for every input the generator can construct. `psf/black` runs
    exactly this idempotency property over `hypothesmith`-generated Python
    source (`psf/black@main`, `scripts` dir, `fuzz.py`).
    A real edge for the reader precisely because the corpus barely uses it —
    0/72 JS/TS, 2/50 Python, and neither Python adopter is a numeric library
    (`pandas`, `scikit-learn`, `jax`) that would benefit most.
    *Enforced by:* review

12. **Contract tests at a service boundary, not a shared integration
    environment.** A contract test asserts "my request shape matches what the
    other service actually accepts" without booting either service — fast,
    fails at the boundary that broke. A shared staging environment both teams
    deploy to catches the same break days later, non-deterministically,
    entangled with everything else deployed that week. `pact-foundation/pact-js`
    is the canonical OSS implementation; it appeared in none of the 72+50+40
    repos measured here — real elsewhere, essentially absent from this corpus.
    *Enforced by:* review

## Verify

```bash
# case-selection checks, diff-scoped (~1-2s on a normal diff)
python3 scripts/test_design_check.py                      # all 8 checks vs HEAD
python3 scripts/test_design_check.py --base origin/main
python3 scripts/test_design_check.py --only sleep,test-name,assert-count
python3 scripts/test_design_check.py --strict              # advisory also fails
python3 scripts/test_design_check.py --max-asserts 6 --max-files 25

# whether the test can fail at all -- owned by minimal-diff, run alongside this
python3 scripts/bloat_check.py --only assertionless,focused-tests

# prove the checker itself still works, false positives included (39 assertions)
bash tests/test_test_design_check.sh
```

## Failure modes

This skill rejects:

- **`test_1`, `test2`, `testFoo`** — numbered or single-word camelCase names
  that name nothing about behaviour. `TestAdd`-shaped Go names are deliberately
  NOT flagged: naming the unit under test rather than a full sentence is the
  sanctioned Go convention (`k3s-io/k3s:tests/TESTING.md` mandates exactly this
  shape via its `gotests` templates), so flagging it would be a false positive
  against real production style, not a catch.
- **A parser test with one hand-picked example** where a property
  (`parse(serialize(x)) == x`) would have caught every malformed input the
  author didn't think of.
- **A mock of `stripe.Charge.create` or `boto3.client`** that asserts call
  arguments — passes today, breaks in production the day the SDK renames a
  kwarg, and the test never noticed because it was testing the mock, not the
  behaviour.
- **Four assertions in one test function**, where the first one failing hides
  whether the other three would also fail — reported as "3 later failures
  hidden," which is what actually costs a debugging session.
- **`time.sleep(2)` in a test** waiting for something to become ready, instead
  of polling or injecting a fake clock — the single most common source of a
  CI-only flaky test.

**Honest limitations, stated per check rather than assumed away:**
- `single-value` is deliberately low precision: it only looks at newly ADDED
  files, skips anything with a table-driven/`parametrize` marker anywhere in
  the file, and requires exactly one test in the file. It will miss a boundary
  gap split across two files and will not catch a modified (not added) file
  that was already missing boundaries before this diff.
- `mock-thirdparty`'s "own vs third-party" line is a directory-name heuristic
  (`local_names()` in the script) — a workspace package two directories deep
  in a monorepo won't be recognised as local, biasing toward over-flagging.
- `test-name`'s JS/TS check is a small explicit phrase blocklist
  (`works`, `should work`, `it works`, …), not a general vagueness detector —
  chosen deliberately narrow so a short-but-real name is never a false
  positive; a vague name outside the blocklist will not be caught.
- Rules 2-4, 10-12 have no mechanical check and are marked `review` honestly —
  pairwise coverage, state-machine completeness, pyramid shape, and contract
  tests all require judgement no diff-scoped regex can supply.

## Next

Choosing cases for code that has no tests yet is `legacy-change` — write the
characterization test first, then apply this skill's rules to what you add
around it. Once tests exist and pass, bind them with `verification-gate`
before claiming done. If the diff also trips `minimal-diff`'s assertionless or
focused-test check, fix that first — a case can't be well-chosen if it can't fail.

## Scale

`solo`: rules 1, 7, 8, 9 — cheap, immediate, and the ones a lone author skips
under time pressure. `small-team (2-10)`: add 5, 6 (double discipline stops
mattering once two people are debugging a mock-coupled test at 2am) and 10
(carrying cost of tests starts being felt as review load). `org (10+)`:
add 2, 3, 12 — pairwise/state-machine/contract-test payoff scales with the
number of combinations and the number of services actually deployed.
`high-blast-radius`: 11 — a parser or serializer with millions of inputs and
one hand-picked example is where property-based testing earns its setup cost.

## Sources

- Mutation testing 0/72 JS/TS, 0/50 Python; patch-coverage gate in exactly 1/72
  (`TriliumNext/Trilium`); property-based testing 2/50 Python
  (`psf/black`, `pydantic/pydantic` — v1 plugin only, removed in v2), 0/72
  JS/TS: `research/30-findings-js-verification.md`,
  `research/31-findings-python-verification.md`.
- Boundary-value table-driven testing at real scale, incl. the exact `uint64`
  max/max+1 boundary pair: `golang/go@go1.22.0:src/strconv/atoi_test.go`.
- Table-driven mandate + naming convention (`Test_Unit<FUNCTION_TO_TEST>`) +
  the 5-layer pyramid named explicitly as white-box vs black-box:
  `k3s-io/k3s@master:tests/TESTING.md`.
- Test-suite naming convention (name for the behaviour under test):
  `google/googletest@main:docs/primer.md`.
- Property-based idempotency at 1000 examples/run, derandomized for CI:
  `psf/black@main`, `scripts` dir, `fuzz.py`.
- Mocking/freezing the clock as an explicit contributor rule, and
  `pytest.mark.parametrize` as the house convention for case variation:
  `apache/airflow@main:contributing-docs/testing/unit_tests.rst`.
- Consumer-driven contract testing, canonical OSS implementation, absent from
  the measured corpus: `pact-foundation/pact-js@master:README.md`.
- `scripts/test_design_check.py`, its 8 diff-scoped checks: `SOURCE: original`
  — the corpus survey found no tool covering case-selection, only execution.
- Assertion-free/focused-test detection this skill deliberately does not
  duplicate: `skills/minimal-diff/SKILL.md`.
