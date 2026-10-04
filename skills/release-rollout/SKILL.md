---
name: release-rollout
description: >
  Production deploy, rollout or release: feature flags, kill switches, canary, roll out
  gradually, rollback plan and triggers, migration ordering, smoke tests. Not for mobile store
  releases (→ mobile-release-safety).
---

# Release rollout

Google SRE attributes roughly 70% of outages to changes in a live system. The
release process is the one place where a defect
that review missed can still be contained: to a flag, to 1% of traffic, to ten
minutes before an automated rollback. Each rule below shrinks the blast radius
or the time to undo. `100x baseline show --work <type> --tier <tier>` prints
which of them a declared tier requires.

## Trigger

**Fire when:** a change will be deployed to users and it touches a schema, a
request hot path, an external integration, a pricing or permission rule, or any
user-visible behaviour; or someone asks how to roll out, roll back, canary or
feature-flag something.

**Do not fire when:** the change is internal tooling, docs, or tests with no
production deploy; or it is a mobile binary (go to `mobile-release-safety`,
which owns store staged rollout and forced upgrade).

## Rules

1. **Ship new behaviour dark, behind a release flag, and plan its removal.** The
   code deploys off; turning it on is a config change, not a deploy. Every
   release flag has an owner and a removal task filed the day it is created,
   because a flag left in place is inventory with a carrying cost.
   *Enforced by:* review

2. **Anything that adds load or depends on a third party gets a kill switch**
   (an ops toggle) that degrades the feature gracefully without a deploy, and
   someone has flipped it once in staging.
   *Enforced by:* review

3. **Order schema changes expand, migrate, contract, in separate deploys.**
   Expand: add the column or table, nullable or defaulted, and deploy code that
   writes both shapes. Migrate: backfill, then switch reads. Contract: drop the
   old shape only after no running version reads it. A `DROP`, `RENAME`, or new
   `NOT NULL` without a default never ships in the same deploy as the code that
   stops depending on it, because the old version is still serving during the
   rollout and is what a rollback returns to.
   *Enforced by:* `! git diff origin/main...HEAD -- '*migrat*' | grep -niE '^\+.*\b(DROP (COLUMN|TABLE)|RENAME (COLUMN|TO)|SET NOT NULL)\b'` (a hit means: split the release, or record why it is safe)

4. **Rollback is a tested command, not a plan.** One command or button returns
   to the previous version; it has been run against staging for this release;
   and the expanded schema from rule 3 means the old code still works after it.
   A data migration that cannot be reversed is called out in the PR as
   one-way, with a restore path (`data-lifecycle`).
   *Enforced by:* review

5. **Canary with pass/fail criteria written before the rollout starts.** Name the
   SLIs (error rate, p95/p99 latency, saturation, and one business metric such
   as checkout success), the threshold for each, the canary population and the
   duration, and compare canary against a control population at the same time
   rather than against yesterday. The population must be large enough and the
   duration long enough to be representative.
   *Enforced by:* review (the criteria live in the PR or the rollout config)

6. **Breaching a canary threshold rolls back automatically.** A human watching a
   dashboard is not a trigger. Encode the thresholds in the rollout controller
   (Argo Rollouts `AnalysisTemplate` with a `failureLimit`, Flagger's metric
   checks, or Spinnaker's Kayenta) so a failed analysis aborts and returns
   traffic to the stable version.
   *Enforced by:* `grep -rlE 'kind: (AnalysisTemplate|Canary)|canaryConfig' --include='*.y*ml' .` (required at the `scale` tier)

7. **Smoke-test production after every deploy and gate promotion on it.** A
   short scripted check of the critical paths (sign in, the main read, the main
   write) runs against the live environment within minutes of the deploy, and a
   failure halts the rollout.
   *Enforced by:* `grep -rqiE 'smoke' .github/workflows package.json` (a smoke step exists), then review

8. **Every release says what changed for users.** A changelog entry, changeset or
   generated release note per user-visible change, including which flag gates
   it, so support and on-call can match a symptom to a release.
   *Enforced by:* `test -f CHANGELOG.md || test -d .changeset || test -f release-please-config.json`

## Verify

Seconds; run before merging a release-bearing PR.

```bash
# rule 3: destructive DDL in the same release as the code change
! git diff origin/main...HEAD -- '*migrat*' | grep -niE '^\+.*\b(DROP (COLUMN|TABLE)|RENAME (COLUMN|TO)|SET NOT NULL)\b'
# rule 7 and rule 8: the pipeline has a smoke step, the repo records releases
grep -rqiE 'smoke' .github/workflows package.json
test -f CHANGELOG.md || test -d .changeset || test -f release-please-config.json
# rule 6, scale tier: automated analysis is configured, not a dashboard
grep -rlE 'kind: (AnalysisTemplate|Canary)|canaryConfig' --include='*.y*ml' .
# the gates that guard the deploy actually gate (security-baseline)
100x audit_ci_gates .
```

These are presence checks. They prove a smoke step, a changelog and an analysis
template exist, not that the thresholds are right or the rollback was exercised.
Rules 1, 2, 4 and 5 are judgement, and the canary criteria belong in the PR body
where a reviewer can disagree with them.

## Failure modes

This skill rejects:

- **A migration that renames `email` to `email_address` in the same deploy as
  the code that reads the new name.** During the rollout, old pods query a
  column that no longer exists; a rollback makes it worse.
- **"We'll watch Grafana for a bit" as the canary plan.** No metric, no
  threshold, no duration, no control group: the canary cannot fail, so it
  proves nothing.
- **A canary judged by comparing today's error rate with last week's.** Traffic
  mix changed; compare against a control running now.
- **A rollback runbook nobody has run**, discovered to need a schema the
  contract step already dropped.
- **A feature flag from two years ago** still branching the checkout code, with
  nobody sure which side is live.
- **A deploy declared done when the pods are healthy**, while sign-in is broken
  for every user because a smoke test was never written.

## Scale

`prototype` / `solo`: rules 3, 4, 8. Expand/contract and a working rollback are
what make an unattended deploy recoverable. `small` (2-10): add 1, 2, 7: a
flag and a kill switch for anything risky, a smoke test after deploy. `growth`
(org 10+): add 5, a manual canary with written criteria. `scale`
(high-blast-radius): add 6, automated canary analysis with automatic rollback;
at that traffic a human cannot react inside the window that matters.

## Sources

- "Roughly 70% of outages are due to changes in a live system", and the three
  answers (progressive rollout, fast detection, safe rollback): Google SRE book,
  ch. 1 "Introduction" (https://sre.google/sre-book/introduction/).
- Canary design, SLI choice, canary versus control, representative population
  and duration: Google SRE Workbook, ch. 16 "Canarying Releases"
  (https://sre.google/workbook/canarying-releases/).
- Release engineering, canary jobs after system tests, exponential cluster
  rollout, configuration under code review: Google SRE book, ch. 8 "Release
  Engineering" (https://sre.google/sre-book/release-engineering/).
- Release, ops (kill switch) and permissioning toggles, toggles as inventory
  with a carrying cost, a removal task per release toggle: Pete Hodgson,
  "Feature Toggles (aka Feature Flags)", martinfowler.com.
- Expand, migrate, contract: Danilo Sato, "ParallelChange", martinfowler.com
  bliki, 13 May 2014.
- Automated analysis that aborts a rollout:
  `argoproj/argo-rollouts@master:docs/features/analysis.md` (a failed
  AnalysisRun aborts and sets canary weight to zero; `failureLimit`);
  `fluxcd/flagger@main:README.md` (metric checks, rollback after max failed
  checks); `spinnaker/kayenta@master:README.md` (automated canary analysis,
  archived and now maintained in the Spinnaker monorepo).
- Tier mapping (which rule starts at which tier): `SOURCE: original`, aligned
  with `scripts/data/scale_tiers.json`.
