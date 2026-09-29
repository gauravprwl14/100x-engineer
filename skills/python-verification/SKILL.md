---
name: python-verification
description: >
  Use when writing, reviewing, or setting up verification for Python code — choosing
  a test/lint/typecheck stack, configuring ruff or mypy, adding coverage or
  pre-commit gates, or deciding what must pass before a Python change ships. Covers
  the measured practice of 50 production Python repositories, including which gates
  actually block CI versus only appear to. Use PROACTIVELY when adding pytest, ruff,
  mypy, pyright, uv, or poetry configuration.
---

# Python verification

What 50 production Python repos (20k+ stars, 250+ commits/yr) actually run, measured
rather than recommended.

## Trigger

**Fire when:** writing or changing Python; setting up or auditing a Python project's
checks; configuring ruff/mypy/pytest/uv; deciding a Python project's merge gates.

**Do not fire when:** the Python file is a one-off script outside a project, or the
task is pure data analysis in a notebook with no shipped artifact.

## The measured baseline

The modal stack — what ~25% of the corpus runs and nothing more:

```bash
uv sync && uv run ruff format --check . && uv run ruff check . && uv run pytest
```

That is a legitimate floor. Ruff is a single binary, sub-second on a diff, and needs
no design decisions. Start here; do not start with the 30-hook pre-commit setups
that large repos have accreted over years.

**The number that matters most:** static type checking is *configured* in 36/50
repos (72%), but only *gates CI* in 27/50 (54%), and runs strict in 8/50 (16%).
Twelve repos have no type-checker config at all — including `django/django` and
`keras-team/keras`. So "we use mypy" is not evidence that mypy can fail your build.

## Rules

1. Run `ruff format --check` and `ruff check` before anything else. It replaces
   black, isort, flake8 and most plugins in one binary.
   *Enforced by:* `uv run ruff format --check . && uv run ruff check .`

2. Pick one type checker and let it gate, or do not have one. A configured-but-
   advisory checker is the worst of both: it costs setup and catches nothing.
   *Enforced by:* `python3 scripts/audit_ci_gates.py` (flags `continue-on-error`,
   `set +e`, `|| true`, `--exit-zero`, `.disabled` workflows)

3. Curate ruff rules with `extend-select`; do not `select = ["ALL"]`. Corpus repos
   that tried ALL ended up with long per-rule ignore lists that nobody maintains.
   *Enforced by:* review

4. Commit a lockfile. `uv.lock` is the fastest-growing choice in the corpus.
   *Enforced by:* `uv lock --check` (or `poetry check --lock`)

5. Make pytest strict about its own configuration: unknown markers and unexpected
   passes should fail, not warn.
   *Enforced by:* `addopts = "--strict-markers --strict-config"` and
   `xfail_strict = true` in `[tool.pytest.ini_options]`

6. Scope type checking honestly. Blocking on a subset you name beats claiming
   repo-wide coverage behind a 90-path ignore list (the `PrefectHQ/prefect` pattern).
   *Enforced by:* `uv run mypy --strict <package>/` on named packages, in CI

7. Validate data at the process boundary, not in the middle. Parse into a typed
   model on the way in.
   *Enforced by:* review

8. For parser, schema, or numeric libraries, add property-based tests. This is the
   corpus's largest unclaimed gap: `pandas`, `scikit-learn` and `jax` all ship
   numerical code and none of them use `hypothesis`.
   *Enforced by:* `uv run pytest tests/property/` once written

9. Do not trust a coverage percentage as proof tests can fail. Mutation testing is
   confirmed absent in 0/50 repos — so the whole corpus shares this blind spot.
   *Enforced by:* `python3 scripts/bloat_check.py --only assertionless`

## Verify

```bash
# what this project has vs the corpus baseline (~1s)
python3 scripts/stack_audit.py .

# do this project's gates actually gate? (~1s) -- run this before trusting green CI
python3 scripts/audit_ci_gates.py .

# minimum viable: the modal corpus stack
uv sync
uv run ruff format --check .
uv run ruff check .
uv run pytest

# strongest justified (org scale / high blast radius)
uv sync --all-extras
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict <package>/          # or pyright/ty/pyrefly -- pick ONE, gate it
uv run pytest --doctest-modules -n auto
uv run pytest --cov=<package> --cov-fail-under=<N>

# bind whichever of the above you rely on to the code being shipped
python3 scripts/verified.py --name test -- uv run pytest
```

Runtime: minimum stack is seconds on a small repo. `mypy --strict` on a large
package is the slow step — scope it per rule 6.

## Failure modes

This skill rejects:

- **`[tool.mypy] strict = true` that CI never invokes.** Verified in
  `invoke-ai/InvokeAI`, whose workflow contains the literal comment
  `# TODO: Add mypy or pyright to the checks.`
- **A lint script run under `set +e`** whose output is posted as a PR comment with no
  exit-code check — so ruff, the type checker and every other linter are advisory.
  Verified in `scikit-learn/scikit-learn`.
- **A type checker that is blocking in form but disabled in substance** —
  `huggingface/transformers` runs `ty` as a required job with 15 rule categories
  switched off, including `unresolved-import` and `invalid-return-type`.
- **A test suite that does not run at all** — `ranaroussi/yfinance` ships
  `.github/workflows/pytest.yml.disabled`.
- **`select = ["ALL"]`** followed by an unmaintained ignore list.
- **A coverage number offered as proof the tests are good.**

## Scale

`solo`: rules 1, 4, 5 — minutes to adopt, immediate return.
`small-team (2-10)`: add 2 and 6 — one gated type checker on named packages.
`org`: add 3, 8, 9 and a coverage floor.
The `vllm`/`pandas`-style 30-hook pre-commit setup with per-CUDA lockfile
regeneration is years of accreted institutional memory. A three-person team copying
it wholesale is cargo-culting, which Part G of the rubric forbids.

## Sources

- All adoption numbers, the six configured-but-not-enforced cases, the eight
  genuinely-strict repos, and both command sequences:
  `research/31-findings-python-verification.md` (50 repos, per-repo citations).
- Corpus selection and gates: `research/10-repo-corpus.md`,
  `research/00-signal-rubric.md`.
- Advisory-gate detection patterns, derived from the six cases above:
  `scripts/audit_ci_gates.py` — `SOURCE: original`.
- `PrefectHQ/prefect`, `ray-project/ray` — the named-subset scoping pattern in rule 6.
