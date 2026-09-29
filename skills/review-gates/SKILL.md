---
name: review-gates
description: >
  Use when setting up or reviewing how changes get merged — PR templates, CODEOWNERS
  path ownership, merge queues, required status checks, DCO or sign-off requirements,
  AI-contribution disclosure trailers, or ADR/release governance. Distinguishes
  checks CI mechanically re-verifies from checkbox ceremony nobody parses. Not for
  the content of a specific diff (see code-review or scoped-review) and not for the
  words inside an AGENTS.md or CLAUDE.md file (see agent-instructions) — this is the
  surrounding merge machinery, not the instructions or the diff itself. Use
  PROACTIVELY when adding a PR template or CODEOWNERS file, or deciding policy on
  AI-authored pull requests.
---

# Review gates

Most review process is theatre. This separates the load-bearing parts from the
ceremony, measured across production repositories.

**The headline: roughly 90% of PR-template checkboxes surveyed are unverifiable** —
nothing parses them, nothing fails when they are wrong. They are a summary at best
and a false comfort at worst.

## Trigger

**Fire when:** writing a PR template or CODEOWNERS; configuring required checks,
merge queues, or sign-off; deciding policy on AI-authored PRs; setting up ADR/RFC
process or release governance.

**Do not fire when:** reviewing the content of a specific diff — that is
`code-review` work, not change-control design.

## Load-bearing vs ceremony

| load-bearing (mechanically blocks) | ceremony (unverifiable or broken) |
|---|---|
| required status checks that CI re-runs regardless of what the PR claims | ~90% of PR-template checkboxes |
| DCO / sign-off parsers | "I tested this locally" |
| Conventional-commit / PR-title bots | "This won't break anything" |
| changeset-file presence checks | honour-system AI-disclosure (6 of 7 policies found) |
| merge queues that actually function | a `merge_group:` trigger that does not |
| per-path CODEOWNERS | single-line catch-all CODEOWNERS |
| trailer-parsing AI-disclosure gates (1 repo) | prose policy with no parser |

The sharpest example of ceremony in the whole study: **`QwenLM/qwen-code` has a
`merge_group:` trigger in its workflow that its own maintainers documented as
non-functional since 2026-07-02** — with a cited production incident (#9220) that a
working merge queue would have caught. The YAML was present. The gate was not.

## Rules

1. Every PR-template item must either be re-verified by CI independently, or be
   explicitly labelled as context for a human. Delete everything else.
   *Enforced by:* review, against the template in Verify below

2. Make CODEOWNERS path-specific. A one-line catch-all routes every review to the
   same team regardless of what changed, which is functionally identical to having
   none.
   *Enforced by:* `test "$(grep -cvE '^\s*(#|$)' .github/CODEOWNERS)" -ge 3`
   (a crude floor; the real test is whether migrations, lockfiles, CI config and
   generated code have distinct owners)

3. Own the risky paths explicitly: database migrations, lockfiles, CI configuration,
   auth code, and generated directories.
   *Enforced by:* named entries for those paths in CODEOWNERS

4. If you declare a merge queue, verify it runs. A present-but-broken gate is worse
   than an absent one because people trust it.
   *Enforced by:* `gh api repos/:owner/:repo/rulesets` (or check a recent merge ran
   through the queue) — verify, do not assume

5. Require sign-off mechanically if you require it at all.
   *Enforced by:* a DCO check app or a workflow that parses commit trailers

6. If a change needs a changeset or release note, check for the file rather than
   asking the author to confirm.
   *Enforced by:* a CI step asserting `.changeset/*.md` exists when publishable
   packages changed

7. For AI-authored contributions, require a machine-checkable trailer and parse it.
   A policy nobody parses is a preference.
   *Enforced by:* a workflow that parses `Assisted-by: <agent>:<model>` trailers and
   fails on violation

8. Demand a reproduction in bug reports. A repo that requires a repro fixes real
   bugs; one that does not accumulates unactionable issues.
   *Enforced by:* a required repro field in the issue template

9. Record rejected proposals, not just accepted ones — and prefer this plugin's own
   `python3 scripts/decide.py new` over a bespoke ADR template, since a rejected
   option is exactly what `decide.py trace` needs later. An ADR directory containing
   only approved decisions loses the reasoning that matters most.
   *Enforced by:* convention

## Verify

```bash
# the fully-verifiable PR template -- every item is CI-backed or labelled unverifiable
mkdir -p .github && cat > .github/PULL_REQUEST_TEMPLATE.md <<'MD'
## What changed and why
<!-- 1-3 sentences. Not machine-verifiable; kept because reviewers need it. -->

## Verification
<!-- These are summaries of gates CI re-runs independently. Do not trust the boxes. -->
- [ ] test command passes — CI-enforced
- [ ] lint/format passes — CI-enforced
- [ ] PR title matches Conventional Commits — CI-enforced by title bot
- [ ] DCO sign-off on every commit — CI-enforced
- [ ] changeset added if public API or deps changed — CI-enforced

## AI assistance
- [ ] If an AI agent materially authored this change, every affected commit carries
      `Assisted-by: <agent>:<model>`.
      <!-- Honour-system unless a trailer parser exists in CI. -->
MD

# audit what you actually have
python3 scripts/stack_audit.py .                 # CODEOWNERS, SECURITY.md, CI presence
python3 scripts/audit_ci_gates.py .              # gates that cannot fail
grep -cvE '^\s*(#|$)' .github/CODEOWNERS         # CODEOWNERS specificity floor

# confirm required checks are real, not just configured
gh api "repos/:owner/:repo/branches/main/protection" --jq '.required_status_checks.contexts' 2>/dev/null \
  || echo "no branch protection readable -- verify in settings"

# AI-disclosure trailer check (rule 7), runnable as a CI step
git log --format='%H %s%n%b' origin/main..HEAD \
  | grep -qE '^Assisted-by: \S+:\S+' \
  || echo "no Assisted-by trailer found on this branch"
```

## Failure modes

This skill rejects:

- **A checkbox nobody parses** presented as a gate — ~90% of surveyed template items.
- **"I tested this locally"** and "this won't break anything": unfalsifiable, so
  deleted per the rubric's anti-goals.
- **A `merge_group:` trigger that does not work** (`QwenLM/qwen-code`, with a named
  incident it should have caught).
- **A one-line CODEOWNERS** — `nuxt` (1 line), `nx` (2), `opentofu` (4), `prisma`
  (1 rule) all technically have one and get no routing benefit from it.
- **An AI-contribution policy with no parser.** 7 of 16 repos in this sample have an
  explicit policy and **only one** (`nextcloud/server`, via
  `.github/workflows/ai-policy.yml`) actually parses commits and fails the build.
- **Migrations and lockfiles with no named owner** — the two highest-blast-radius
  paths in most repos.

**Honest limitations:**
- The load-bearing/ceremony counts come from a **partial sample** (16 repos in the
  completed batch, not the full governance worklist). The direction is clear and the
  named examples are verified; treat the percentages as indicative, not final.
- Branch-protection and ruleset configuration is **not visible in a clone**. Anything
  about required checks has to be verified against the API or the settings UI, which
  is why rule 4 says verify rather than assume.
- Policy text has proliferated faster than the behaviour it asks for: AI-disclosure
  policies are now common while disclosure trailers remain rare.

## Next

For the decision log this rule 9 points at, retrieval is `python3 scripts/ledger.py
find "<term>"` or `python3 scripts/decide.py trace <path>`. Once merge mechanics are
in place, `verification-gate` is what actually blocks a bad merge at commit time;
this skill only builds the surrounding process. Writing the instruction file itself
is `agent-instructions`, a different skill.

## Scale

`solo`: rule 8 only. A PR template reviewed by nobody is pure overhead; a bug repro
requirement still pays.
`small-team (2-10)`: add 1, 2, 3, 6 — path-specific CODEOWNERS on migrations,
lockfiles and CI config is the highest-value item at this size.
`org (10+)`: add 4, 5, 7, 9 and a functioning merge queue — active in 5 of 16 repos
in this sample, all of them larger projects.

## Sources

- Load-bearing/ceremony split, PR-template survey, CODEOWNERS quantification, merge
  queue and AI-policy counts, and the drafted template:
  `research/37-findings-review-governance.md`.
- `nextcloud/server:.github/workflows/ai-policy.yml` — the only CI-enforced
  AI-disclosure gate found (rule 7).
- `mochajs/mocha:.github/workflows/slop-detection.yml` — CI-enforced AI-quality gate.
- `QwenLM/qwen-code` — non-functional `merge_group:` with incident #9220.
- `prisma/prisma`, `nextcloud/server`, `prometheus/prometheus` — DCO enforcement.
- `nuxt/nuxt`, `payloadcms/payload` — PR-title format bots.
- `QwikDev/qwik` — changeset-file presence check (rule 6).
- `ray-project/ray`, `vllm-project/vllm` — verbatim shared policy banning pure-agent
  PRs; an org-scale position, recorded in
  `research/21-findings-agent-instruction-corpus.md`.
- Rejected-proposal retention (rule 9): no repo in `research/37` was found recording
  rejected ADRs specifically — `SOURCE: original`, inferred from ADR practice
  generally rather than measured in this corpus.
