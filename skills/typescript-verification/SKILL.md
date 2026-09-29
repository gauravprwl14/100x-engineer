---
name: typescript-verification
description: >
  Use when writing, reviewing, or setting up verification for JavaScript or
  TypeScript code specifically — tsconfig strictness, ESLint/Biome rule curation,
  vitest/jest, pnpm/Turborepo/Nx monorepo task graphs, knip dead-code detection,
  size-limit bundle budgets, or patch-scoped coverage gates. Covers the measured
  practice of 72 production JS/TS repositories. Not for Python or Go toolchains
  (see python-verification, go-verification), and not for framework-specific code
  idioms like a NestJS pipe or a React list key (see stack-reviewer). Use
  PROACTIVELY when adding package.json scripts, tsconfig.json, or a JS/TS CI
  workflow.
---

# TypeScript verification

What 72 production JS/TS repos actually run, counted rather than recommended.

## Trigger

**Fire when:** writing or changing JS/TS; setting up or auditing a JS/TS project's
checks; configuring tsconfig, eslint/biome, vitest/jest, turbo/nx; deciding merge
gates.

**Do not fire when:** editing a JSON/YAML config with no code impact, or working in
a non-JS part of a polyglot repo.

## The measured baseline

Modal stack: **pnpm** (53%) + **vitest** (56%) + **ESLint** (74%) + **Prettier**
(61%), with root `test` / `lint` / `typecheck` scripts. Turborepo beats Nx and Lerna
**2.3:1** among monorepos.

Minimum viable, and genuinely what most of the corpus runs:

```bash
pnpm lint && pnpm typecheck && pnpm test
```

**The absences are the story.** Across 72 production repos:

| practice | adoption |
|---|---|
| coverage gate of any kind | 14% (86% have none) |
| bundle-size budget | 3% (97% have none) |
| knip (dead code / unused exports) | 10/72 |
| merge queue (`merge_group`) | 8/72 — all tier-1/tier-2 |
| `api-extractor` + committed `.api.md` | 1/72 |
| **patch-scoped blocking coverage gate** | **1/72** |
| mutation testing | **0/72** |
| property-based testing | **0/72** |
| `isolatedDeclarations` | **0/72** |
| no root `test` script at all | 5/72 |

So if you add patch-scoped coverage or property tests, you are ahead of nearly the
entire 20k-star JS ecosystem — not catching up to it.

## Rules

1. Set `"strict": true` in tsconfig. It is the highest-value single flag and the
   corpus baseline.
   *Enforced by:* `npx tsc --noEmit`

2. Run typecheck as its own fast gate, separate from build. A ~10s type-error check
   catches most breakage long before a full build would.
   *Enforced by:* `npx tsc --noEmit` as a distinct CI job and package script

3. Gate coverage on the **patch**, not the repo. A whole-repo threshold is
   unmeetable on an existing codebase and gets disabled; patch coverage asks only
   that new code be tested.
   *Enforced by:* codecov `patch:` status with `informational: false`, or
   `diff-cover` against the merge base

4. Add `knip` to find unused files, exports and dependencies. It is the strongest
   single anti-bloat tool for this ecosystem.
   *Enforced by:* `npx knip`

5. Enforce architectural boundaries mechanically if you have more than one package.
   Prose about layering does not survive contact with an agent.
   *Enforced by:* `turbo boundaries`, `dependency-cruiser --output-type err`, or
   `eslint-plugin-boundaries`

6. Budget bundle size for anything you ship to a browser, and pick the number
   yourself — 97% of the corpus has no budget, so there is no default to inherit.
   *Enforced by:* `npx size-limit`

7. In a monorepo, run only affected work. Full-graph CI on every PR trains people to
   ignore CI.
   *Enforced by:* `turbo run test --filter=...[origin/main]`

8. Never suppress the type-checker to make CI pass. `@ts-ignore` and `any` hide the
   bug the checker just found.
   *Enforced by:* `@typescript-eslint/no-explicit-any` and
   `@typescript-eslint/ban-ts-comment` enabled in eslint

9. Verify your gates actually gate before trusting green CI.
   *Enforced by:* `python3 scripts/audit_ci_gates.py`

10. Consider `noUncheckedIndexedAccess`. Array and record access returning
    `T | undefined` is correct, and catches a real bug class — adopted by very few
    corpus repos, so expect friction on an existing codebase.
    *Enforced by:* the flag in tsconfig plus `npx tsc --noEmit`

## Verify

```bash
# minimum viable -- the modal corpus stack
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck          # or: npx tsc --noEmit
pnpm test

# strongest justified (tier-1 shape)
npx tsc --noEmit
npx eslint . --max-warnings=0
npx vitest run --coverage
npx knip                                        # unused files, exports, deps
npx dependency-cruiser --config .dependency-cruiser.cjs --output-type err src
npx size-limit                                  # if you ship a bundle
npx madge --circular --extensions ts,tsx src    # import cycles
turbo run test --filter=...[origin/main]        # monorepo: affected only

# patch-scoped coverage (rule 3) -- the practice only 1 of 72 repos has
npx vitest run --coverage --coverage.reporter=cobertura
diff-cover coverage/cobertura-coverage.xml \
  --compare-branch=$(git merge-base HEAD origin/main) --fail-under=80

# project state vs the measured corpus
python3 scripts/stack_audit.py .
python3 scripts/audit_ci_gates.py .

# bind the checks to the code being shipped
python3 scripts/verified.py --name typecheck -- npx tsc --noEmit
python3 scripts/verified.py --name test      -- pnpm test
```

`--max-warnings=0` matters: eslint exits 0 with warnings by default, so a
warnings-only config is not a gate.

## Failure modes

This skill rejects:

- **A repo with no root `test` script.** Five corpus repos have none — including
  `supabase/supabase`, `ToolJet/ToolJet`, `mozilla/pdf.js`, `immich-app/immich` and
  `sveltejs/kit`. Popularity does not imply a runnable prove-it command.
- **A whole-repo coverage threshold on a large existing codebase.** It fails on day
  one, so it gets set to 0 or deleted. Patch-scoped gating is the version that
  survives.
- **`informational: true`** on a codecov status — it looks like a gate and cannot
  fail.
- **`eslint .` without `--max-warnings=0`** presented as a lint gate.
- **`@ts-ignore` added to make CI green.**
- **Layer rules that live only in a README.** `reactive-resume` is the only corpus
  repo with a machine-enforced cross-package import boundary (Turborepo `boundaries`
  plus Grit) — everyone else documents the intent and lets it erode.
- **Unbounded bundle growth** — measured by 3% of the corpus, budgeted by almost
  none.

**Honest limitations:** mutation and property-based testing are absent from all 72
repos (and from all 50 Python repos measured separately). So the ecosystem has no
standard answer to "can these tests actually fail?", and neither does this skill
beyond `bloat_check.py --only assertionless`.

## Next

Bind whichever commands you chose to the code being shipped with
`verification-gate`. If a rule here (patch-coverage threshold, a banned `any`
exception, a bundle-size number) departs from the corpus baseline, log it:
`python3 scripts/decide.py new "<the choice>" --affects "<glob>"`. If the diff is
inside NestJS, Next.js, React Native, or another tracked framework, apply
`stack-reviewer` too — this skill covers the toolchain, not the code shape.

## Scale

`solo`: rules 1, 2, 8 — strict mode and a separate typecheck job, minutes to adopt.
`small-team (2-10)`: add 3, 4, 9 — patch coverage and knip.
`org`: add 5, 6, 7, and a merge queue (8/72 corpus adoption, exclusively tier-1/2).
`react/react` caches per-shard timing to rebalance CI as the suite grows; that is an
org-scale answer to an org-scale problem, not a starting point.

## Sources

- All counts, the modal stack, tier-1 differentiators and both command sequences:
  `research/30-findings-js-verification.md` (72 repos, per-repo citations).
- `TriliumNext/Trilium` — the single corpus repo with a patch-scoped blocking
  coverage gate (rule 3).
- `TanStack/table` — a 30KB `size-limit` budget on `table-core` (rule 6).
- `reactive-resume` — Turborepo `boundaries` + Grit as a build gate (rule 5).
- `facebook/react` — shard-timing cache for CI rebalancing (Scale).
- `vercel/next.js:AGENTS.md` — "~10s type-error check, faster than build" (rule 2).
- `elastic/kibana:AGENTS.md` — "Never suppress type errors with @ts-ignore… fix the
  root cause" (rule 8).
