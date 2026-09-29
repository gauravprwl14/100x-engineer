---
name: root-cause-analysis
description: >
  Use when something IS broken in production, an incident happened, or a test is
  mysteriously failing and the cause is not yet obvious — not for a bug you already
  understand (use bug-fix directly for that). Separates symptom from trigger from
  mechanism from root cause, reconstructs a timeline, forces falsifiable hypotheses
  before belief, runs an honest five-whys with a stated stop condition, and gates on
  producing a regression test plus a check of whether an existing decision's
  assumption silently stopped holding. Use PROACTIVELY after any incident, outage,
  or hard-to-explain failure, before writing the fix.
---

# Root cause analysis

Most "root cause analyses" stop at the trigger: "it broke because we deployed." A
deploy is never a root cause — it is what exposed one. This skill forces the chain
one step further, and gates on the two things an RCA actually owes the org: a
regression test, and an honest check of whether a documented decision's assumption
quietly stopped being true. `rca.py link` exists specifically for that connection —
`decide.py drift` finds decisions whose governed code moved; a silently-violated
assumption is one of the most common root causes there is.

## Trigger

**Fire when:** production is or was broken, an incident occurred, a test fails
intermittently or in CI-only, or the cause of a bug is not obvious after one
reproduction attempt.

**Do not fire when:** the bug is understood after reproducing it once and the fix is
local — that is `bug-fix`, which is lighter-weight by design. Firing this on every
one-line bug turns a diagnostic tool into ceremony, which is exactly what gets RCA
abandoned.

## Rules

1. Reproduce before theorizing. An RCA built on an assumed mechanism instead of a
   reproduced one is fiction with a timeline attached.
   *Enforced by:* `python3 scripts/rca.py lint` rejects a record with no reproduction

2. Separate **symptom** (what was observed), **trigger** (the immediate event),
   **mechanism** (how the trigger produces the symptom, step by step), and **root
   cause** (the underlying condition) into four distinct statements. A root cause
   that restates the symptom means the chain never actually ran.
   *Enforced by:* `python3 scripts/rca.py lint` rejects a root cause identical to the
   symptom, and rejects a missing symptom/trigger/mechanism

3. Reconstruct the timeline before theorizing about mechanism — `git log`,
   `git bisect`, deploy times. Cross-check whether a decision's assumption stopped
   holding underneath the code first.
   *Enforced by:* `python3 scripts/rca.py lint` rejects no timeline;
   `python3 scripts/decide.py drift` finds decisions whose governed code moved

4. State each hypothesis with what evidence would **falsify** it, before going to get
   that evidence. Reject the first-plausible-cause trap — the first story that fits
   the symptom is rarely checked against alternatives, only confirmed.
   *Enforced by:* `python3 scripts/rca.py lint` rejects hypotheses with no stated
   falsifying evidence

5. Run five-whys honestly, with a stated stop condition — and know its failure mode:
   it forces a single causal chain, when real incidents usually have several
   conditions acting together. That is what rule 6 is for.
   *Enforced by:* `python3 scripts/rca.py lint` rejects fewer than 2 real levels

6. Record contributing factors distinct from the root cause. An empty section here
   claims the root cause acted completely alone, which is rarely true — the "why
   did this reach production" conditions (missing test coverage, a reviewer
   unfamiliar with the flow, an alert that didn't fire) belong here, not folded into
   the root cause itself.
   *Enforced by:* `python3 scripts/rca.py lint` rejects an empty contributing-factors
   list

7. The output must name the regression test, and state whether an existing
   decision's assumption was violated. These are what an RCA is actually for —
   everything above exists to earn them honestly.
   *Enforced by:* `python3 scripts/rca.py lint` rejects no regression-test reference;
   `python3 scripts/rca.py link RCA-000X --decision ADR-000Y` records the assumption
   check

8. Keep it blameless. Name the process gap, not the person — "no gate catches a
   SameSite change against the SSO flow" survives being read by the person who wrote
   it; "X forgot to check the SSO flow" does not, and it teaches nothing reusable.
   *Enforced by:* review

## Verify

```bash
# open a record for the incident
python3 scripts/rca.py new "Sessions dropped after deploy" --affects "src/auth/**" --severity high

# reconstruct the timeline
git log --oneline --since="2026-09-28" -- src/auth
git bisect start; git bisect bad HEAD; git bisect good <last-known-good-sha>
python3 scripts/decide.py drift          # decisions whose governed code moved since recorded

# completeness gate — the point of this skill
python3 scripts/rca.py lint

# if an existing decision's assumption turns out to be the cause
python3 scripts/rca.py link RCA-0001 --decision ADR-0001 --assumption A1

# regenerate the index, never hand-maintained
python3 scripts/rca.py index

# then fix it, with the RCA's regression_test as the failing test bug-fix commits first
```

## Failure modes

This skill rejects:

- **A root cause identical to the symptom** — "it crashed because it crashed" wearing
  RCA formatting.
- **Stopping at the trigger** — "a deploy happened" with no mechanism connecting the
  deploy to the symptom.
- **A five-whys chain with one level**, or one that never states why it stopped where
  it did.
- **A hypothesis presented as fact**, with no falsifying evidence ever sought — the
  first plausible story, unchecked against alternatives.
- **An empty contributing-factors section**, implying a single clean cause when the
  timeline usually shows several conditions compounding.
- **An RCA that never checks whether an existing decision's assumption was the
  actual cause** — flagged as a warning by `rca.py lint`, because whether one exists
  to check is not always knowable mechanically, but its absence is visible in the
  index.
- **No regression test reference** — the incident can recur and nothing will fail.
- **Blame language substituting for a process finding** — caught by review, not by
  any script; see Honest limitations.

**Honest limitations:**
- `rca.py lint` checks structure and non-placeholder content, not truth. A hypothesis
  can claim `falsify_with: "reproduced locally"` without that reproduction having
  actually happened — same honest limitation `decide.py verify` states about its own
  assumption commands.
- The five-whys stop condition is required to be *stated*, not judged. A chain that
  stops one level too early, with a plausible-sounding stop condition, passes lint.
  That is rule 8's neighbor: review, not a script, catches a stop condition that is
  really just "ran out of patience."
- Blamelessness is enforced by review only. Nothing mechanically distinguishes "the
  reviewer missed the SSO interaction" (blame) from "no check exists for
  cookie-attribute changes against the SSO flow" (process finding) — the second is
  what this skill is for, and only a human or a review pass can tell them apart.

## Scale

`small-team (2-10)` and up is where this pays for itself over `bug-fix` alone — a
solo maintainer often does hold the whole timeline in their head, in which case the
lighter `bug-fix` loop is enough. It becomes essential at `high-blast-radius`
(production outages, security incidents, payment paths), where the decision-link
check (rule 7) is frequently the actual finding: a documented assumption quietly
stopped holding, and nothing before this record connected the two.

## Sources
- The regression-test-as-deliverable framing, and the fuzz-finding-to-regression-test
  loop it generalizes: `google/oss-fuzz@2cc3fa4:docs/advanced-topics/ideal_integration.md`,
  `sqlite/sqlite@86876d2:test/fuzzcheck.c` — both cited in full in
  `research/35-findings-security-reliability.md`.
- Required blameless retrospective within 1-3 days of a security release, citing
  Google's SRE postmortem-culture doc: `envoyproxy/envoy@72e8b00:SECURITY.md`,
  described in `research/35-findings-security-reliability.md`.
- The symptom/trigger/mechanism/root-cause split, falsifiable-hypothesis discipline,
  the five-whys single-chain failure mode, and the decide.py-drift integration as the
  mechanism for catching a silently-violated assumption: `SOURCE: original` — no
  single repo in the corpus encodes this taxonomy as a checked artifact; it is this
  plugin's synthesis of the blameless-postmortem and fuzz-corpus practices above,
  made mechanically checkable via `rca.py lint`.
