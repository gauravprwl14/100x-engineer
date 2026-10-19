---
name: minimal-diff
description: >
  Bloated diff — too many new files, dead or commented-out code, tests that assert nothing,
  speculative abstractions, unrequested docs, agent bloat, reformatting: keep the change small.
  Not for merge policy (→ review-gates).
---

# Minimal diff

The default failure of an AI writing code is not that it writes wrong code. It is
that it writes **too much** code: extra files, extra layers, extra docs, extra
dependencies, tests that cannot fail. Each addition is individually defensible and
collectively fatal.

## Trigger

**Fire when:** adding a feature, fixing a bug, refactoring, or reviewing a diff.

**Do not fire when:** scaffolding a genuinely new project from zero (there is no
existing code to prefer), or when the user explicitly asked for a new module,
document, or dependency.

## Rules

1. Prefer editing an existing file over creating a new one. A new file needs a
   reason you can state in one sentence.
   *Enforced by:* `100x bloat_check --only file-creation-ratio` (advisory)

2. Never add a dependency without first checking the stdlib and the existing
   dependency list. State what you checked, and if you add one anyway, log why:
   `100x decide new "Add <package>" --affects "package.json"`.
   *Enforced by:* `git diff HEAD -- package.json pyproject.toml go.mod` reviewed in the
   diff; `depcheck` / `deptry .` / `go mod tidy && git diff --exit-code` in CI

3. Do not add an abstraction until the second caller exists. An interface with one
   implementation is a guess about the future.
   *Enforced by:* `100x bloat_check --only single-use-abstraction` (advisory —
   the tool flags it, a human decides load-bearing vs speculative)

4. Delete dead code rather than commenting it out. Version control is the archive.
   *Enforced by:* `100x bloat_check --only commented-code`

5. Every test must be able to fail. A test that calls code without asserting is a
   coverage lie. Two independent research passes found **no production repo** with a
   mechanical check for this, so the check here has no prior art to imitate.
   *Enforced by:* `100x bloat_check --only assertionless`

5b. Never commit a focused or silently-skipped test. `it.only` disables every other
   test in its file; a skip with no stated reason is a permanent hole.
   *Enforced by:* `100x bloat_check --only focused-tests`
   (`jest/no-focused-tests` and equivalents are the one near-universal real gate in
   production)

6. Do not create documentation that was not requested. No `ARCHITECTURE.md`, no
   `NOTES.md`, no summary of what you just did.
   *Enforced by:* `100x bloat_check --only new-docs`

7. A `TODO` without an issue reference is a note to nobody. Reference an issue or
   fix it now.
   *Enforced by:* `100x bloat_check --only bare-todo`

8. Never reformat lines you did not otherwise change. Format only changed files, so
   a reviewer sees logic and not whitespace.
   *Enforced by:* `npx prettier --check $(git diff --name-only --diff-filter=ACM origin/main)`
   — the diff-scoped form. A full-repo format check is blind to this failure mode by
   construction; `angular/angular`'s `ng-dev format changed --check <base-sha>` is the
   cleanest production example found (1 of 8 repos checked).

9. Do not widen a public API as a side effect. An export is a permanent promise.
   *Enforced by:* `api-extractor` committed `.api.md` golden diff, or
   `tsc --declaration` + `git diff --exit-code`

10. Comments explain *why*, never *what*. If the comment restates the code, delete
    one of them.
    *Enforced by:* review — no tool resolves this (see Failure modes)

## Verify

```bash
# diff-scoped: safe to run on a large existing codebase (~1-3s)
100x bloat_check                       # all checks vs HEAD
100x bloat_check --base origin/main    # whole-branch view
100x bloat_check --strict              # advisory findings also fail

# language-specific dead code / dependency creep — pick what the repo has
npx knip                                             # unused files, exports, deps
npx depcheck                                         # unused dependencies
npx madge --circular --extensions ts src             # import cycles
ruff check .                                         # F401 unused imports, ERA dead code
vulture src/ --min-confidence 80                     # unused Python code
deptry .                                             # Python dependency issues
golangci-lint run                                    # Go unused
go mod tidy && git diff --exit-code go.mod go.sum    # Go dependency drift

# prove the checker itself still works (13 assertions, ~3s)
bash tests/test_bloat_check.sh
```

## Failure modes

This skill rejects:

- **A test that calls code and asserts nothing** — verified detection in Python,
  JavaScript/TypeScript and Go. This is the highest-value check here: such a test
  raises coverage while proving nothing, so it actively misleads.
- **Commented-out code added in a diff** — dead on arrival.
- **`ARCHITECTURE_OVERVIEW.md` nobody asked for** — the classic agent reflex of
  documenting its own work as a deliverable.
- **Four new `Handler` classes where one function would do** — flagged as advisory,
  because distinguishing a speculative interface from a deliberate extension seam
  genuinely requires judgement.
- **`# TODO: fix later`** with no issue reference.

**Where this skill stands relative to production practice.** Two independent research
passes — tool-isolation testing, then reading real configs in ~46 repos — classified
the 12 AI-bloat failure modes. Five have **no mechanical coverage in any production
repo read**: new-file-instead-of-edit, single-use abstractions, semantic duplication,
redundant comments, and assertion-free tests. `scripts/bloat_check.py` covers four of
those five (the first two as advisory signals, since they need judgement; assertion-free
tests fully, across Python, JavaScript and Go). Semantic duplication remains
uncovered here too.

Conversely, four modes *are* well covered by existing tools — dead code, banned-
dependency re-adds, import cycles/layer violations, and (weakly) size budgets — so
rules 2, 4 and 9 delegate to `knip`, `depguard` and `dependency-cruiser` rather than
reimplementing them.

**What no tool catches, stated plainly** (measured, not assumed — see Sources):
- **Whether a new dependency was actually necessary.** Tools make the addition
  visible and blockable; they cannot judge need.
- **Semantic duplication with renamed variables.** Copy-paste detectors miss it —
  two functions with identical logic and different variable names score 0%
  duplication. This is precisely the duplication shape LLMs produce most.
- **Whether a comment restates the code.** Needs semantic understanding of both.
- **Cumulative cross-PR bloat.** A thousand diffs each just under budget still grow
  a codebase without limit. Only trend tracking sees it, and trend tracking only
  reports.

Route those four to a human or to an LLM review pass scoped *only* to those
questions — not asked to re-derive what the mechanical checks already settled.

## Next

Once the diff is small, run `verification-gate` to bind a real check to it, then
the matching language skill (`language-verification`) for what "real" means on this stack. If the diff touches a
framework with known LLM failure shapes, `stack-reviewer` catches what bloat
checking cannot.

## Scale

`solo` and up. The file-creation and assertionless checks matter most for solo and
small-team work, where no reviewer is reading every diff. Rules 9 (API surface) and
2 (dependency policy) start earning their cost at `small-team (2-10)` and become
essential at `org`.

## Sources

- The 12 AI-bloat failure modes, the tool matrix, and the negative results on what
  no tool catches: `research/23-findings-antibloat-enforcement.md` — tooling
  executed against planted-violation repositories, results labelled TESTED/UNTESTED.
- Real production configs behind rules 2, 8 and 9, incl. two independent repos
  banning `github.com/pkg/errors` in favour of stdlib via `depguard`:
  `traefik/traefik`, `prometheus/prometheus` — see the same document.
- "Prefer implementing functionality in existing files unless it is a new logical
  component. Avoid creating many small files." — `zed-industries/zed:.rules`
- "Do not write organizational or comments that summarize the code. Comments should
  only be written in order to explain 'why'..." — `zed-industries/zed:.rules`
  (rule 10)
- Recurring corpus rules behind 1, 2, 8 (prefer editing over creating; check
  existing deps first; scoped diffs only): `research/21-findings-agent-instruction-corpus.md`
- `scripts/bloat_check.py`, its six diff-scoped checks and 13-assertion suite:
  `SOURCE: original` — built because the survey found no tool covering these shapes.
