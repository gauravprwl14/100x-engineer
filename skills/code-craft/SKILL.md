---
name: code-craft
description: >
  Use when writing or reviewing a function, class, or module and deciding its
  SHAPE — naming, function length, parameter count, nesting depth, error
  handling, coupling, mutability, and primitive obsession (raw number/string
  used for money, ids, durations). Complements minimal-diff, which covers diff
  VOLUME (too much code); this is about whether the code that exists reads as
  clean, senior-engineer work. Use PROACTIVELY after writing a function and
  before opening a PR, and during scoped-review's R-question pass.
---

# Code craft

`minimal-diff` catches an AI writing *too much* code. Nothing in this plugin
addressed the complaint a staff/principal reviewer actually raises: not "why
is this file here" but "why does this function have seven parameters, four
nesting levels, and a variable named `data`." That is a senior engineer's
primary lever, and it was entirely process-and-verification until this skill.

## Trigger

**Fire when:** writing or changing a function/class/module; reviewing a diff
for shape rather than correctness; a PR touches financial amounts, ids, or
durations (primitive obsession matters most there).

**Do not fire when:** the diff is pure config/data/generated code with no
hand-written logic — there is no shape to review.

## Rules

1. Names reveal intent. No `data`/`info`/`manager`/`helper`/`util`/`temp`/
   `obj`/`val`/`thing`/`stuff`/`handle`/`process` as the primary noun;
   booleans read as predicates (`is_active`, not `active`); abbreviate only
   established domain terms; match the surrounding codebase over personal
   preference.
   *Enforced by:* `python3 scripts/craft_check.py --only vague-names` (advisory,
   stoplist only) + review for predicates/abbreviations/consistency.

2. One level of abstraction per function — extract until each function reads
   at one altitude, not a mix of "validate," "parse," and `i = i + 1`.
   *Enforced by:* review — see `reviewers/_code-craft.md` for the shape.

3. Function length has a threshold, not a hard cap. Default 60 lines (real
   range 40-100, see Sources); Google's own guidance is "no hard limit...
   think about it," which is why this stays advisory.
   *Enforced by:* `python3 scripts/craft_check.py --only function-length`
   (advisory).

4. Parameter count has a threshold too (default 5). When a function's
   parameters always travel and change together, reach for a parameter
   object instead of adding a sixth loose value.
   *Enforced by:* `python3 scripts/craft_check.py --only param-count`
   (advisory).

5. No boolean flag parameters that select behaviour at the call site
   (`save(1, True)`). A keyword-only flag that just toggles one line of
   output, not a code path, is fine.
   *Enforced by:* `python3 scripts/craft_check.py --only boolean-flag-arg`
   (advisory).

6. Return early over nested conditionals (guard clauses); no flag variable
   threaded through loops in place of nested `if`s. Nesting depth threshold
   default 4.
   *Enforced by:* `python3 scripts/craft_check.py --only nesting-depth`
   (advisory).

7. A module has one reason to change; dependency direction points inward
   (core never imports an adapter). No reaching through a collaborator to
   its collaborator's collaborator — Demeter, stated concretely in
   `reviewers/_code-craft.md`, not as a slogan.
   *Enforced by:* `python3 scripts/craft_check.py --only demeter-chain`
   (advisory, chain-depth heuristic) + review for dependency direction.

8. Errors are a typed taxonomy, translated at the edge, never swallowed. An
   `except`/`catch` with an empty or log-only body and no re-raise is a bug,
   not a style choice.
   *Enforced by:* `python3 scripts/craft_check.py --only bare-except`
   (**blocking**).

9. Distinguish expected failure (a `Result`/`Either` or a checked domain
   error the caller must handle) from a bug (a precondition violation —
   `throw`/`panic`, don't catch-and-continue).
   *Enforced by:* review.

10. Comments explain why, not what — the mechanical half of this (a comment
    restating the code) is `minimal-diff` rule 10; this skill adds the shape
    argument that a function needing such a comment usually needs renaming
    or splitting instead.
    *Enforced by:* review (cross-referenced, not duplicated).

11. Prefer immutable data at a module's boundary; name and detect hidden
    temporal coupling (a caller must invoke A before B with nothing in the
    signature saying so) rather than leaving it implicit.
    *Enforced by:* convention.

12. A money amount, an id, and a duration are types, not `number`/`string`/
    `float`. This matters most in fintech/bank code: a `float` for money is
    a latent rounding bug, not a style preference.
    *Enforced by:* `python3 scripts/craft_check.py --only money-as-float`
    (advisory).

13. Parallel operations look parallel; an argument-order or naming inversion
    between sibling operations (`create(ctx, id)` vs `delete(id, ctx)`) is a
    smell independent of which order is "correct."
    *Enforced by:* convention.

## Verify

```bash
# diff-scoped: safe to run on a large existing codebase (~1-3s)
python3 scripts/craft_check.py                        # all checks vs HEAD
python3 scripts/craft_check.py --base origin/main
python3 scripts/craft_check.py --strict                # advisory findings also fail
python3 scripts/craft_check.py --only vague-names,money-as-float,bare-except
python3 scripts/craft_check.py --func-len 80 --params 6 --depth 5

# the reference doc for every rule above, with a before/after example
sed -n '1,40p' reviewers/_code-craft.md

# prove the checker itself still works (65 assertions incl. 32 clean-file
# false-positive checks, ~2s)
bash tests/test_craft_check.sh
```

## Failure modes

This skill rejects:

- **`def process(data): manager = data.get("items"); return manager`** — three
  vague nouns doing the work that `summarize_order`/`line_items` should.
- **`save(1, True)`** — a bare positional boolean nobody can read at the call
  site without opening `save`'s body to learn what `True` selects.
- **`except Exception: pass`** — the exact failure mode `bloat_check.py`'s
  assertionless-test check targets, applied to error handling: evidence of a
  bug destroyed on purpose.
- **`order.customer.address.city.upper()`** — a Demeter violation that
  couples a shipping-label formatter to `Customer`'s and `Address`'s
  internal shape.
- **`def charge(amount: float)`** — a money amount typed as a binary float,
  which cannot represent `19.99` exactly; the correct-money-type argument
  from `reviewers/_code-craft.md` is what a fintech reviewer checks first.
- **Four levels of nested `if` where three guard clauses would do** —
  `nesting-depth` and `boolean-flag-arg` together catch the control-flow
  shape `minimal-diff` (diff volume) does not look at.

## Scale

`solo` and up. Naming, function shape, and error-swallowing matter for a
solo author as much as a team — the reviewer is the author's future self.
Cohesion/coupling and dependency-direction rules start paying for themselves
at `small-team (2-10)`, once a second person owns adjacent code. Primitive
obsession for money/ids is `high-blast-radius` regardless of team size — a
rounding bug in a bank ledger costs the same whether one engineer wrote it or
ten reviewed it.

## Sources

Full citations with `owner/repo@ref:path` for every threshold are in
`reviewers/_code-craft.md`. Summary of what was actually found, not invented:

- Function length: `google/styleguide@gh-pages:pyguide.md` §3.18 gives a SOFT
  ~40-line prompt with "no hard limit"; ESLint's documented
  `max-lines-per-function` default (50) ships `off` in
  `airbnb/javascript@master`; `rust-lang/rust-clippy`'s
  `too-many-lines-threshold` defaults to 100 and is enforced by inheritance
  in `zed-industries/zed`.
- Parameter count: ESLint `max-params` default 3, `off` in
  `airbnb/javascript` and `facebook/react@main:.eslintrc.js`; clippy's
  `too-many-arguments-threshold` defaults to 7, enforced in `zed`.
- Nesting depth: ESLint `max-depth` default 4, `off` in both surveyed
  adopters; clippy's `excessive-nesting-threshold` defaults to **0
  (disabled)** unless a project opts in — nobody surveyed enforces a nesting
  number by default except via ESLint's unused default.
- Cyclomatic complexity: `golangci-lint`'s `gocyclo` defaults to 30 (its own
  docs recommend 10-20); `grafana/grafana` enables it unconfigured (inherits
  30); `prometheus/prometheus` does not enable it at all.
- Demeter-chain depth, vague-name stoplist, money-as-float, boolean-flag-arg:
  `SOURCE: original` — no surveyed repo enforces any of these mechanically;
  stated as an explicit absence finding, not papered over.
- `scripts/craft_check.py`'s 8 diff-scoped checks and
  `tests/test_craft_check.sh`'s 65 assertions: `SOURCE: original`, built
  because the survey found no tool covering code *shape* the way
  `bloat_check.py` covers diff *volume*.
