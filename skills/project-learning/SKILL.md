---
name: project-learning
description: >
  Use when a mistake cost time, a non-obvious convention was discovered, or a failure
  mode was hit that will recur — recording it as a project lesson that outlives the
  conversation. Also use before editing an unfamiliar file, to recall lessons already
  recorded for it. Not for recording a design choice with alternatives, which is
  decision-log, and not for a production incident, which is root-cause-analysis.
---

# Project learning

A conversation ends and everything it learned evaporates. The next session rediscovers
that the test suite needs a running Postgres, that a generated file must never be hand
edited, that this service's clock is UTC while its neighbour's is local. Each
rediscovery costs the same hour.

A lesson is the cheapest artifact in this plugin and the one with the longest half-life.

## Trigger

**Fire when:** something surprised you and will surprise the next person; a convention
was discovered rather than documented; a failure mode was hit; you are about to edit a
file you do not know well.

**Do not fire when:** the thing is already recorded — in the code, in git history, in
`CLAUDE.md`, or in an existing lesson. Duplicating what the repo already says makes the
lesson store noise, and a noisy store stops being read.

## What a lesson is, and is not

| this is a lesson | this is not |
|---|---|
| "The integration suite needs `docker compose up db` first; it fails with a confusing DNS error otherwise" | "We use Postgres" — that is in the code |
| "`src/generated/` is rebuilt by `make proto`; hand edits are silently reverted" | "Don't edit generated code" — that is a convention for `AGENTS.md` |
| "Rate limiter counts per-IP, so local testing from one machine trips it after 5 requests" | "We chose Redis over Memcached" — that is a decision, use `decide.py` |
| "Migration 0042 must run before 0043 despite the numbering, because it backfills a column 0043 indexes" | "The deploy broke on Tuesday" — that is an RCA |

The test: **would this have saved you time if you had read it first?** If not, it is not
a lesson.

## Rules

1. Record a lesson the moment it costs you time. Not at the end of the task, when the
   specific detail has blurred into a general feeling.
   *Enforced by:* `python3 scripts/learn.py add "<lesson>" --kind <k> --affects "<glob>"`

2. Every lesson needs an `--affects` glob. A lesson nobody can find from the file it
   applies to will never be read again.
   *Enforced by:* `python3 scripts/learn.py lint`

3. Every lesson needs a source — an ADR id, an RCA id, or a `file:line`. An unsourced
   lesson cannot be re-checked when the code moves.
   *Enforced by:* `python3 scripts/learn.py lint`

4. State the observable trigger, not a preference. "Prefer clean code" is unusable;
   "the linter fails with X unless Y is set first" is actionable.
   *Enforced by:* `python3 scripts/learn.py lint` (rejects a vague preference with no
   observable trigger)

5. Recall before editing an unfamiliar file. This is the half of the loop that pays —
   writing lessons nobody reads is a diary.
   *Enforced by:* `python3 scripts/learn.py relevant <path>`

6. Do not record what the repo already records. Code structure, git history and
   `CLAUDE.md` are not lessons.
   *Enforced by:* review

7. Delete a lesson that stops being true. A stale lesson is worse than none, because it
   is trusted.
   *Enforced by:* `python3 scripts/learn.py lint` flags a lesson whose source path no
   longer exists

## Verify

```bash
# record it, with where it applies and where it came from
python3 scripts/learn.py add \
  "Integration suite needs docker compose up db first; otherwise it fails with a DNS error" \
  --kind gotcha --affects "tests/integration/**" --source "tests/integration/conftest.py:14"

# recall it — run this before editing an unfamiliar file
python3 scripts/learn.py relevant tests/integration/test_orders.py

# browse and audit
python3 scripts/learn.py list --kind gotcha
python3 scripts/learn.py lint          # no affects, no source, or vague preference
python3 scripts/learn.py index         # regenerates lessons/INDEX.md

# lessons appear in the ledger alongside decisions and RCAs
python3 scripts/ledger.py find "docker compose"
```

Kinds: `gotcha` (it will bite again), `convention` (discovered, not documented),
`failure` (what broke and why), `preference` (a team choice with no stronger backing).

## Failure modes

This skill rejects:

- **A lesson with no `--affects`** — unreachable from the code it concerns, so it is
  write-only.
- **A lesson with no source** — cannot be re-verified when the code moves, so it decays
  into folklore.
- **"Prefer descriptive names"** — a preference with no observable trigger. Not a lesson.
- **"We use NestJS"** — already in `package.json`.
- **A design choice with alternatives** — that is `decision-log`; a lesson has no
  rejected options.
- **A production incident** — that is `root-cause-analysis`, which also demands a
  timeline and a regression test.
- **A lesson whose source file no longer exists**, flagged by `lint` as probably stale.

**Honest limitations:**
- **Nothing forces recall.** `learn.py relevant` must be run; no hook injects lessons
  into context automatically. That is the biggest weakness of this design, and it is
  why rule 5 exists rather than a mechanism.
- **Matching is glob-based.** A lesson tagged `src/auth/**` will not surface for a
  caller in `src/api/` that depends on it.
- **This is not Claude Code's memory.** It is a project-local, git-tracked, reviewable
  store that travels with the repository. Claude Code's own memory is per-user and
  separate; this plugin does not write to it.

## Scale

`solo` and up, and the value is highest at `solo` — there is no colleague who remembers
the gotcha. At `small-team` the store becomes onboarding material. At `org` rule 7
matters most: an unmaintained lesson store is trusted and wrong.

## Sources
- Lesson records use the same `json meta` fence as decisions and RCAs so `ledger.py`
  discovers them: `scripts/learn.py`, `scripts/ledger.py` — `SOURCE: original`.
- The rule against storing what the repo already records is the memory discipline in
  `research/21-findings-agent-instruction-corpus.md` (rule 12: defer to authoritative
  docs rather than duplicating them).
- Repro-as-permanent-artifact, the same idea applied to tests:
  `research/35-findings-security-reliability.md`.
