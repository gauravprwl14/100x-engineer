# Python verification — detail

Reference for `language-verification` (loaded on demand). The numbered rules live in `../SKILL.md`; rule numbers below refer to that file.

What 50 production Python repos (20k+ stars, 250+ commits/yr) actually run, measured
rather than recommended.

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

## Verify

```bash
# what this project has vs the corpus baseline (~1s)
100x stack_audit .

# do this project's gates actually gate? (~1s) -- run this before trusting green CI
100x audit_ci_gates .

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
100x verified --name test -- uv run pytest
```

Runtime: minimum stack is seconds on a small repo. `mypy --strict` on a large
package is the slow step — scope it per rule 16.

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

## Next

Bind the commands you chose with `verification-gate`. If the diff is inside a
framework this plugin tracks, `stack-reviewer` catches code-shape bugs this skill
does not. Deleted since the last pass: a "validate at the process boundary" rule —
generic software-design advice, unsourced to any repo in `research/31`, and not
specific to what makes a Python *verification* setup real versus advisory.

## Scale

`solo`: rules 11, 14, 15 — minutes to adopt, immediate return.
`small-team (2-10)`: add 12 and 16 — one gated type checker on named packages.
`org`: add 13, 17, 18 and a coverage floor.
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
- `PrefectHQ/prefect`, `ray-project/ray` — the named-subset scoping pattern in rule 16.
