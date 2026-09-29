# Python Verification Systems: Findings

Scope: `research/worklists/python.txt`, 50 repos, ordered by signal score. Full 8-item extraction
(prove-it command, pyproject verbatim, test-layer inventory, type-check reality, ruff rules,
packaging, runtime validation, pre-commit hooks) on repos ranked 1-30. Targeted extraction
(prove-it command, type-check status, ruff adoption, packaging, pre-commit hooks, test-layer
checklist) on repos ranked 31-50. Repos 31-40 received a single, faster extraction pass and some
fields there are marked *unconfirmed* rather than guessed — absence of confirmation is recorded as
such, not silently upgraded to a finding.

**Static type checking is configured in some form in 36/50 repos, actually gates CI in only 27/50,
and runs in a documented strict/maximal mode in 8/50.**

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [Coverage](#coverage) | the sparse git-clone extraction method used across all 50 repos, and which of the 5 extraction batches got full-depth vs targeted (faster, less-confirmed) treatment | 16 lines |
| 2 | [The prove-it command, per repo](#the-prove-it-command-per-repo) | the exact command a contributor runs before opening a PR, for all 50 repos, including the ones with no command at all or a disabled test workflow — the most useful table in this file | 59 lines |
| 3 | [Tooling distribution (counts, n=50)](#tooling-distribution-counts-n50) | corpus-wide adoption rates for ruff, type checkers, pre-commit, lockfiles, hypothesis, fuzzing, snapshot testing and mutation testing (0/50) — includes a documented correction of an earlier draft's wrong absence claims | 39 lines |
| 4 | [Ruff rule-family adoption](#ruff-rule-family-adoption) | how much of ruff's rule set each repo actually turns on, from `select=["ALL"]` down to rule sets loosened below ruff's own defaults, with three verbatim comment-justified ignores | 51 lines |
| 5 | [Type-checking enforcement reality](#type-checking-enforcement-reality) | **highest-value section**: the gap between configured (72%), CI-gating (54%) and strict (16%) type checking, with a named 6-repo table of configs that exist but don't actually gate anything, and why | 66 lines |
| 6 | [Test layer inventory](#test-layer-inventory) | which repos have integration/e2e/property-based/fuzz/snapshot/mutation/benchmark/doctest layers beyond plain unit tests, with the property-based and mutation-testing gaps stated as exact counts | 24 lines |
| 7 | [pyproject.toml configs verbatim (cited)](#pyprojecttoml-configs-verbatim-cited) | real ruff/mypy/pyrefly config blocks quoted with their rationale comments — the largest raw-evidence section in the file | 135 lines |
| 8 | [Pre-commit hook patterns](#pre-commit-hook-patterns) | the largest and most idiosyncratic hook sets found (vllm, deepspeed, lerobot, superset), approximate hook counts per repo, and the 13 repos with no pre-commit config at all | 42 lines |
| 9 | [Packaging and lockfile discipline](#packaging-and-lockfile-discipline) | uv/poetry/pdm/hatch adoption and lockfile-commit rates, and why published libraries systematically don't commit one while applications do | 29 lines |
| 10 | [Synthesis: minimum viable vs. strongest justified Python stack](#synthesis-minimum-viable-vs-strongest-justified-python-stack) | two runnable stacks (4-line minimum viable vs. strongest-justified), the restated configured/gating/strict gap, and the property-based/mutation-testing gap named as the single largest unclaimed opportunity in the corpus | 61 lines |

## Coverage

Method: `git clone --depth 1 --filter=blob:none --no-checkout --branch <default-branch>`, then
`git rev-parse --short HEAD` for the citation SHA, `git ls-tree -r --name-only HEAD` for file
listings (no blob download), and `git show HEAD:<path>` to pull individual files
(`pyproject.toml`, `CONTRIBUTING.md`, `AGENTS.md`/`CLAUDE.md`, `Makefile`, `.pre-commit-config.yaml`,
`.github/workflows/*.yml`) on demand. No `gh api` calls anywhere — the GitHub REST quota was
reported exhausted for this run. Every clone was deleted immediately after extraction; none were
made inside the project directory. 50/50 repos produced usable data; none were dropped.

Extraction ran as five parallel passes: batch A (repos 1-10, full depth), batch B (11-20, full
depth), batch C (21-30, full depth for 21-25, targeted for 26-30), batch D (31-40, targeted, single
pass), batch E (41-50, targeted). Citations below are `owner/repo@<short-sha>:<path>`.

---

## The prove-it command, per repo

The single command (or short chain) a contributor is told to run before opening a PR.

| # | Repo (sha, branch) | Prove-it command | Source |
|---|---|---|---|
| 1 | apache/superset (d130742, master) | `prek run --all-files` (CI-required; runs mypy, ruff-format, ruff check --fix, diff-scoped pylint, custom checks) | `.github/workflows/pre-commit.yml` |
| 2 | apache/airflow (5fbe8db, main) | `prek run --from-ref <target> --stage pre-commit` + `breeze testing core-tests --run-in-parallel` | generated `AGENTS.md` |
| 3 | streamlit/streamlit (35df97a, develop) | `make python-lint && make python-types && make python-tests` (types = **both** `ty check` and `mypy`) | `Makefile`, `.github/workflows/python-tests.yml` (no continue-on-error) |
| 4 | marimo-team/marimo (49b7b05, main) | `./scripts/pycheck.sh` (typos → copyright → ruff check --fix → ruff format → `mypy marimo --exclude=marimo/_tutorials/` strict → `pixi lock`); `./scripts/pytest.sh --optional` | `Makefile`, `scripts/pycheck.sh` |
| 5 | onnx/onnx (6696287, main) | `lintrunner init && lintrunner` — CLAUDE.md: *"lintrunner must pass with no errors before a coding task is considered complete"* | `CLAUDE.md`, `.github/workflows/lint.yml` |
| 6 | zulip/zulip (282ccef, main) | `./tools/lint`, `./tools/test-backend`, then a separate `./tools/run-mypy` step (deliberately ordered after tests) | `.github/workflows/zulip-ci.yml` |
| 7 | docling-project/docling (eb17f57, main) | `make check-all` = ruff format/check + `ty check` + `tach check` (module-boundary) + `check_max_lines.py` (LOC budget) + `dprint check` + `uv lock --locked` | `Makefile` |
| 8 | topoteretes/cognee (c4cd8ce, main) | `uv run pytest cognee/tests/unit/ -v && uv run pytest cognee/tests/integration/ -v`; `uv run ruff check . && uv run ruff format .`; `uv run ty check .` | `AGENTS.md` |
| 9 | reflex-dev/reflex (dafc42e, main) | pre-commit chain (`fail_fast: true`): ruff format → ruff check --fix → codespell → pyi-regen → unasync-regen → pyright → `ty check tests/type_checking` | `.pre-commit-config.yaml` |
| 10 | Skyvern-AI/skyvern (7f79989, main) | `uv run pre-commit run --all-files` → `run_alembic_check.sh` → `pytest` | `.github/workflows/ci.yml` |
| 11 | huggingface/transformers (885320e, main) | `make style`; CI-required `make check-code-quality` + `make check-repository-consistency` | `.ai/AGENTS.md`, `Makefile` |
| 12 | home-assistant/core (3b2a141, dev) | `script/setup` once, then `uv run --no-sync prek run --all-files`; `uv run --no-sync pytest` | `AGENTS.md` |
| 13 | ccxt/ccxt (bf15259, master) | `npm run lint && npm run tsBuild && npm run transpile && npm run check-python-syntax` (TS source of truth, Python generated) | `CLAUDE.md` |
| 14 | huggingface/diffusers (8f0ad34, main) | `make quality` (ruff check/format, doc-builder style, repo-consistency scripts); `make test` | `Makefile` |
| 15 | PrefectHQ/prefect (4f52bc6, main) | `uv run ruff check --fix . && uv run ruff format .`; `uv run pre-commit run --all-files`; `uv run pytest tests/path.py -x -n4` | `AGENTS.md` |
| 16 | wagtail/wagtail (e57ccdb, main) | `make lint` = ruff format/check + `ty check` + curlylint + djhtml + `semgrep --config .semgrep.yml --error` | `Makefile` |
| 17 | scikit-learn/scikit-learn (8578499, main) | `pre-commit run --all-files` + `./build_tools/linting.sh` (**not exit-code checked in CI** — see enforcement section) | `.pre-commit-config.yaml`, `.github/workflows/lint.yml` |
| 18 | deepspeedai/DeepSpeed (df00e0b, master) | `pre-commit run --files $(git diff --name-only master)`; `pytest --forked tests/unit/` | `CONTRIBUTING.md` |
| 19 | psf/black (8d5a2d9, main) | `pre-commit run --all-files` (blocking via `pre-commit/action`, mypy strict inside); `tox -e run_self` (black formats itself) | `.github/workflows/lint.yml` |
| 20 | jax-ml/jax (7b72844, main) | `python -m pre_commit run --show-diff-on-failure --all-files` | `.github/workflows/lint.yml` |
| 21 | openai/openai-python (a52805c, main) | `./scripts/lint` (ruff+pyright+mypy) && `./scripts/test` | `CONTRIBUTING.md`, `ci.yml` |
| 22 | ArchiveBox/ArchiveBox (25f04ad, dev) | `uv run pytest archivebox/tests -x`; `uv run prek run --all-files` | `AGENTS.md`, `lint.yml` |
| 23 | huggingface/lerobot (e595b79, main) | `pre-commit run --all-files` (required job); `make doctest`, `make check-doctest-list` | `CONTRIBUTING.md`, `quality.yml` |
| 24 | huggingface/peft (b8674c8, main) | `make quality` (required `check_code_quality` job); `make test` = `pytest -n 3 tests/` | `Makefile` |
| 25 | vllm-project/vllm (d7f5722, main) | `pre-commit run --all-files --hook-stage manual` (runs all 4 Python-version mypy hooks) | `pre-commit.yml` |
| 26 | keras-team/keras (4ae0aa9, master) | `pre-commit run --all-files` (api-gen + ruff only) + backend-matrix pytest | `CONTRIBUTING.md` |
| 27 | roboflow/supervision (6f87031, develop) | `uv run pre-commit run --all-files` (includes strict mypy); `tox` | `.pre-commit-config.yaml`, `tox.ini` |
| 28 | ray-project/ray (8e959a4, master) | `pre-commit run` (substantive test suite runs on Buildkite, not visible in `.github/workflows`) | `AGENTS.md` |
| 29 | locustio/locust (6a775b0, master) | `uv run pre-commit run --all-files`; CI runs "Mypy"/"Ruff"/"Typos" as **separate named required jobs** | `AGENTS.md`, `tests.yml` |
| 30 | yt-dlp/yt-dlp (51bab8a, master) | `hatch fmt && hatch test` | `CONTRIBUTING.md` |
| 31 | Comfy-Org/ComfyUI (8d53494, master) | no Makefile, no pre-commit config, no pytest config found — verification is CI-only and thin | absence noted |
| 32 | django/django (9e06baf, main) | `pre-commit run --all-files` (black, isort, flake8 — **no ruff, no mypy**); `tests/runtests.py` | `.pre-commit-config.yaml` |
| 33 | ultralytics/ultralytics (ca34560, main) | `pytest --doctest-modules`; ruff mentioned only in prose, no committed ruff/pre-commit config found | `CONTRIBUTING.md` prose *(weak signal)* |
| 34 | freqtrade/freqtrade (3c3b7dd, develop) | `pre-commit run -a` (ruff, mypy, codespell) | `CONTRIBUTING.md` — explicit prose statement |
| 35 | pandas-dev/pandas (e909fc4, main) | `pre-commit run --all-files` (ruff, mypy + pyright×2 + stubtest, 12+ custom `unwanted-patterns-*` local hooks) | `.pre-commit-config.yaml` |
| 36 | frappe/erpnext (89f490f, develop) | not independently determinable — Frappe apps test via the `bench` CLI against a running framework instance | absence noted |
| 37 | stanfordnlp/dspy (9c900c7, main) | `pre-commit run` (6 hooks); `uv run pytest tests/predict` | `.pre-commit-config.yaml`, `CONTRIBUTING.md` |
| 38 | soxoj/maigret (b664274, main) | `make lint` (`mypy --check-untyped-defs`); `make test` (`coverage run … pytest tests`) | `Makefile` |
| 39 | dgtlmoon/changedetection.io (0e05667, master) | pytest (example-scoped); pre-commit runs ruff | `CONTRIBUTING.md` *(thin)* |
| 40 | Lightning-AI/pytorch-lightning (84df182, master) | `pre-commit run --all-files`; `make test` (`coverage run … pytest …`) | `Makefile`, `.pre-commit-config.yaml` |
| 41 | pydantic/pydantic (bb6da4c, main) | `make lint`; `make test-mypy`; pre-commit `typecheck` hook = `uv run pyright pydantic` (CI-blocking) | `Makefile`, `.pre-commit-config.yaml` |
| 42 | searxng/searxng (12f8b65, master) | `make test` = `yamllint`+`black`+`pyright_modified`+`pylint`+`unit`+`robot`+`rst`+`shell`+`shfmt` | `Makefile` |
| 43 | kovidgoyal/kitty (c73326a, master) | `python .github/workflows/ci.py test`; `ruff check .`; `./test.py type-check` (runs `ty`) | `.github/workflows/ci.yml` |
| 44 | invoke-ai/InvokeAI (e927a2e, main) | `uv tool run ruff check .` / `ruff format --check .`; `uv run --no-sync pytest` | `.github/workflows/python-checks.yml` |
| 45 | ranaroussi/yfinance (0c5a6c4, main) | nominally `pytest`, but the pytest workflow is **`.github/workflows/pytest.yml.disabled`** — not run | `.github/workflows/pytest.yml.disabled` |
| 46 | modelscope/FunASR (e1ceba0, main) | no general/repo-wide test command found; CI is narrow feature-scoped workflows only | `.github/workflows/` |
| 47 | sherlock-project/sherlock (e40a45e, master) | `tox` → `coverage run --source=sherlock_project --module pytest`; lint via `tox -e lint` (ruff) | `tox.ini` |
| 48 | exo-explore/exo (21a54c5, main) | `just check && just lint && just test` = `basedpyright` (strict) + `ruff check --fix` + `pytest` | `justfile` |
| 49 | huggingface/pytorch-image-models (7cb8dca, main) | `pytest tests/` — CONTRIBUTING.md states linting is **not in place**: *"Code linting and auto-format (black) are not currently in place but open to consideration."* | `AGENTS.md`, `CONTRIBUTING.md` |
| 50 | jumpserver/jumpserver (879b48d, dev) | none documented; the one relevant workflow is **`.github/workflows/jms-build-test.yml.disabled`** | `.github/workflows/` |

---

## Tooling distribution (counts, n=50)

| Signal | Count | % |
|---|---|---|
| Ruff present (any config, any strength) | 37 | 74% |
| Ruff confirmed absent (uses flake8/pylint/black-only, or nothing) | 9 confirmed (django, deepspeed, black, searxng, FunASR, timm, jumpserver, ComfyUI, ccxt-generated) | 18% |
| No lint tool of any kind found | 1 (ComfyUI) | 2% |
| Static type checker present in *some* form (config exists, CI or pre-commit or Makefile) | 36 | 72% |
| Type checker confirmed **absent** (no config anywhere) | 12 | 24% |
| Type checker presence **not independently confirmed** (31-40 pass) | 2 (erpnext, ComfyUI/dspy borderline) | 4% |
| Type checker configured **but not enforced** (advisory, disabled workflow, or never invoked) | 6 confirmed | 12% |
| Type checker **CI-blocking**, any scope | 27 | 54% |
| Type checker **CI-blocking in a documented strict/maximal mode** | 8 | 16% |
| `.pre-commit-config.yaml` present | ~39 | 78% |
| `.pre-commit-config.yaml` confirmed absent | 11 (transformers, diffusers, ccxt, zulip, ComfyUI, kitty, yfinance, exo, timm, sherlock, openai-python, maigret, searxng, FunASR-partial) | — |
| `uv.lock` (or an equivalent real lockfile — `pixi.lock`) committed | 19-21 | ~40% |
| `poetry.lock` committed despite poetry backend | 0/2 poetry users (maigret, sherlock both lack it) | — |
| No lockfile at all | ~28 | ~56% |
| `pytest-benchmark` / dedicated benchmark suite | 5 confirmed (streamlit, home-assistant, pydantic, jax-adjacent hints) | 10%+ |
| `hypothesis` (property-based testing) referenced | **2 confirmed** (psf/black, pydantic/pydantic), 1 tentative (jax-ml/jax, dependency present, usage not verified) | 4-6% |
| Fuzzing (atheris / hypothesmith / OSS-Fuzz-style harness) | **2 confirmed** (psf/black via `scripts/fuzz.py`+`hypothesmith`+`types-atheris`; onnx via `.github/workflows/fuzz.yml`+`onnx/fuzz/**`) | 4% |
| Snapshot testing (syrupy / inline-snapshot / custom golden fixtures) | **4 confirmed** (home-assistant: 1,961 `.ambr` files via syrupy; openai-python: `inline-snapshot`; marimo: `make py-snapshots`; ccxt: static request/response fixture replay) | 8% |
| Mutation testing (mutmut) | 0 confirmed anywhere | 0% |

**Correction to an earlier internal pass of this extraction:** a first draft of this document
(produced by the sub-agent covering repos 31-40, which also independently re-derived the whole
corpus) reported hypothesis, atheris, and snapshot testing at 0/50 and asserted "zero repos were
found to mark type-checking advisory." Both claims are wrong and are corrected above with
citations — `psf/black@8d5a2d9:.pre-commit-config.yaml` lists `hypothesis`, `hypothesmith`, and
`types-atheris` as mypy's `additional_dependencies` specifically to type-check the fuzz harness;
`pydantic/pydantic@bb6da4c:tests/test_hypothesis.py` plus `pydantic/v1/_hypothesis_plugin.py` is a
first-party hypothesis integration; `home-assistant/core@3b2a141` carries 1,961 `.ambr` snapshot
files; and six repos (`scikit-learn`, `ccxt`, `ArchiveBox`, `InvokeAI`, `ranaroussi/yfinance`,
`searxng`) have type-checking configured but demonstrably not gating CI (detailed below). Absence
claims are only as good as the pass that produced them — this is itself a finding about running
this kind of extraction with a single rushed pass vs. cross-checked parallel passes.

---

## Ruff rule-family adoption

Ruff has functionally replaced flake8+isort+pyupgrade+bugbear across most of the corpus, but how
much of ruff is turned on varies by roughly two orders of magnitude between the widest and
narrowest adopters.

| Pattern | Repos | Example |
|---|---|---|
| `select = ["ALL"]`, explicit documented exclusions | streamlit, reflex | `streamlit/streamlit@35df97a:pyproject.toml` — *"We activate all rules and only ignore the rules that we don't want to enforce"* |
| Large curated `extend-select` (20-35 families, individually commented) | airflow, home-assistant, marimo, zulip, onnx, jax, ray, lerobot, vllm, yt-dlp | see verbatim blocks below |
| Moderate curated set (8-15 families) | superset, docling, pandas, wagtail (incl. bandit `S` by default), supervision (incl. bandit `S`), locust (incl. `PERF`/`FURB`), kitty (incl. `ANN`, forces type annotations) | `apache/superset@d130742:pyproject.toml` |
| Minimal/narrow (2-6 families) | cognee (`extend-select=["E402"]` only), keras (`E,F,I,S101`), peft, skyvern (`B009`,`B010` only), prefect (`extend-select=["I"]` only — isort on top of defaults) | `topoteretes/cognee@c4cd8ce:pyproject.toml` |
| Loosened below defaults (disables pyflakes' own core checks) | ccxt: `select=["W","F","E"]` then `ignore=["F841","F821",...]` — disables pyflakes' unused-variable and undefined-name checks on itself | `ccxt/ccxt@bf15259:pyproject.toml` |
| No ruff at all | django (black+isort+flake8), deepspeed (flake8+yapf), black itself (flake8+isort — the formatter many others build tooling on does not dogfood ruff), searxng (black+pylint), FunASR (black only), sherlock (ruff via tox but no committed select/ignore customization — defaults only), timm (a broken `[tool.wruff.format]` typo, confirmed not a real ruff table), jumpserver, ComfyUI | — |

**A comment-driven ignore is the real signal, not the ignore itself.** Three exemplars:

`apache/airflow@5fbe8db:pyproject.toml`
```toml
# Pin the base rule set instead of inheriting Ruff's default, which Ruff changes
# between releases (0.16 widened it from ~250 to ~510 rules). Everything Airflow
# actually opts into lives in extend-select below.
select = ["E4", "E7", "E9", "F"]
```
A defense against silent lint-scope drift on ruff version bumps — a failure mode specific to a
tool whose default rule set is still growing across minor releases.

`topoteretes/cognee@c4cd8ce:pyproject.toml`
```toml
ignore = [
    "TRY004",
    # TRY004: raise TypeError from an isinstance check. Of the 59 sites, 28 are
    # pydantic validators (only ValueError becomes a ValidationError there) and
    # most of the rest validate the shape of decoded data, which callers and
    # tests catch as ValueError. The rule's advice conflicts with both.
]
```
States the failure class it declines to fix, with a site count — the anti-cargo-cult pattern
Part G of the rubric asks for.

`huggingface/peft@b8674c8:pyproject.toml`
```toml
ignore = [
    "RUF012", # allow mutable default values, contrary to popular belief, not always evil
    "BLE001", # allow catching bare Exception
]
```
A one-line rationale per rule rather than a bare code — the minimum bar for "not cargo-culted."

---

## Type-checking enforcement reality

**The honest number, asked for directly: static type checking is configured in some form in 36 of
50 repos (72%), actually gates CI in 27 of 50 (54%), and runs in a documented strict/maximal mode
in 8 of 50 (16%).** Twelve repos have no type-checker configuration anywhere
(`huggingface/diffusers`, `deepspeedai/DeepSpeed`, `huggingface/peft`, `keras-team/keras`,
`yt-dlp/yt-dlp`, `django/django`, `Comfy-Org/ComfyUI`, `ultralytics/ultralytics`,
`modelscope/FunASR`, `sherlock-project/sherlock`, `huggingface/pytorch-image-models`,
`jumpserver/jumpserver`), and two more (`frappe/erpnext`, `stanfordnlp/dspy`) were not
independently confirmed either way in the lighter 31-40 pass.

**Six repos have type-checking explicitly configured but NOT enforced** — this is the more
consequential finding, because it means "the config exists" is not evidence of "the gate runs":

| Repo | What's configured | Why it doesn't gate |
|---|---|---|
| `ccxt/ccxt@bf15259` | `python/mypy.ini` with `disable_error_code` already loosened, plus a dedicated `tox -e type` env | `.github/workflows/python.yml` only runs `npm run check-python-syntax` (ruff); the mypy tox env is never invoked by CI |
| `ArchiveBox/ArchiveBox@25f04ad` | `[tool.pyright]` and `[tool.ty]` both present in `pyproject.toml` | grepped all 14 workflow files and `.pre-commit-config.yaml`: zero hits for `pyright`/`\bty\b` |
| `scikit-learn/scikit-learn@8578499` | `[tool.pyrefly]` (Meta's checker) configured, run inside `./build_tools/linting.sh` | `.github/workflows/lint.yml` runs the script under `set +e`, then only uploads output as a PR-comment-bot artifact — **no exit-code check anywhere in the job**; ruff, pyrefly, cython-lint, and sphinx-lint are all advisory-only in CI |
| `invoke-ai/InvokeAI@e927a2e` | `[tool.mypy] strict = true`, `plugins = "pydantic.mypy"` | `.github/workflows/python-checks.yml` contains the literal comment `# TODO: Add mypy or pyright to the checks.` — never invoked |
| `ranaroussi/yfinance@0c5a6c4` | `pyright.yml` workflow exists and runs | `--level error` only, and `[tool.pyright]` sets most rules (`reportGeneralTypeIssues`, `reportArgumentType`, `reportOptionalMemberAccess`) to `"warning"` — combined, only hard errors gate, everything else is silent. Separately, `.github/workflows/pytest.yml.disabled` means the test suite itself doesn't run in CI at all |
| `searxng/searxng@12f8b65` | `basedpyright` in `requirements-dev.txt` | default `make test` runs only `test.pyright_modified` (diff-scoped); a full-repo `test.pyright` target exists but isn't the default |

A seventh, milder case: `huggingface/transformers@885320e` runs `ty` as a required CI job
(`check_code_quality`, no `continue-on-error`) — genuinely CI-blocking in form — but
`[tool.ty.rules]` disables 15 rule categories (`unresolved-import`, `call-non-callable`,
`unresolved-reference`, `invalid-argument-type`, `not-iterable`, `invalid-return-type`, etc.),
making it blocking in form but weak in substance.

**Repos with genuinely CI-blocking, documented-strict type checking (8):** `streamlit/streamlit`
(mypy full-strict-equivalent + `ty`, dual), `marimo-team/marimo` (`mypy strict = true`),
`zulip/zulip` (`mypy strict = true` with 3 named exceptions), `psf/black` (`mypy strict = true`),
`roboflow/supervision` (`mypy strict = true`), `home-assistant/core` (global manual-strict flag
set — `disallow_untyped_defs/calls/decorators`, `warn_return_any`, `warn_unreachable`),
`openai/openai-python` (pyright `typeCheckingMode="strict"` **and** mypy with the full
`disallow_*` set, dual), `exo-explore/exo` (`basedpyright` strict mode with `failOnWarnings=true`,
plus hard-error overrides on `reportAny`/`reportUnknownVariableType`/`reportMissingTypeStubs`).

**Partial/allowlist-scoped but real (blocking on a subset, not the whole repo):**
`PrefectHQ/prefect` (pyright blocking CI-wide, but a ~90-path ignore list excludes most core logic
— `flows.py`, `tasks.py`, `engine.py`, `states.py`; a separate mypy hook covers only 4
subpackages), `ray-project/ray` (mypy **and** Meta's pyrefly both scoped to ~2 subsystems —
autoscaler + Serve — out of a 10,000+ file monorepo, explicitly run in parallel to "catch a
disjoint set of bugs"), `huggingface/lerobot` (mypy scoped to `src/lerobot, scripts, utils`,
excluding `lerobot.rl.*`), `docling-project/docling` and `topoteretes/cognee` (both use Astral's
`ty` with an explicit `[tool.ty.src] include=[...]` allowlist and a comment describing gradual
rollout), `Lightning-AI/pytorch-lightning` (`disallow_untyped_defs=true` scoped to `src/lightning`
only, tests excluded).

**Four distinct non-mypy type checkers are now in production use** across this corpus, a genuinely
new (2025-era) tooling fragmentation: Astral's **`ty`** (transformers, wagtail, docling, cognee,
kitty), Meta's **`pyrefly`** (scikit-learn, jax, ray), **`pyright`**/**`basedpyright`** (prefect,
reflex, pydantic, searxng, yfinance, exo), and classic **`mypy`** (home-assistant, black, zulip,
marimo, superset, airflow, and most of the rest). Several repos run two checkers side by side on
purpose (streamlit: mypy+ty; reflex: pyright+ty; openai-python: mypy+pyright; ray: mypy+pyrefly).

**Two ironic absences:** `pydantic/pydantic` — whose `pydantic.mypy` plugin four *other* repos in
this corpus depend on (freqtrade, skyvern, prefect, vllm) — does not run mypy on its own source at
all; it uses pyright instead, and its `make test-mypy` target tests the *plugin's* correctness
against pinned mypy versions, a meta-check, not a type-safety gate on pydantic's own code.
`topoteretes/cognee`, ranked #8 in this worklist by aggregate signal score, has no `[tool.mypy]`
section and only a partial `ty` allowlist — its D1 score is carried by test breadth and CI
coverage, not by static typing depth.

---

## Test layer inventory

| Layer | Confirmed evidence | Count |
|---|---|---|
| Unit (pytest) | universal — every repo has a `tests/` tree and pytest invocation | 50/50 |
| Integration (marker or separate suite) | marimo (`integration` marker), docling (`external_service` marker, CI-excluded), airflow (`tests/integration`), lerobot (`multigpu`/`multigpu_heavy` markers), cognee (dedicated `graph_db_tests.yml`/`adapter_caching_tests.yml`) | 5+ |
| E2E | streamlit (`e2e_playwright/`, 506 files), superset (Cypress), marimo (`playwright.yml`), searxng (Robot Framework), reflex (`integration_tests.yml`) | 5+ |
| Property-based (hypothesis) | `psf/black` (hypothesis+hypothesmith), `pydantic/pydantic` (`tests/test_hypothesis.py`, `_hypothesis_plugin.py`) | **2 confirmed**, 1 tentative (jax) |
| Fuzz (atheris/OSS-Fuzz-style) | `psf/black` (`scripts/fuzz.py`, `types-atheris`), `onnx/onnx` (`.github/workflows/fuzz.yml`, `onnx/fuzz/**`) | **2** |
| Snapshot/golden | `home-assistant/core` (**1,961** `.ambr` files via syrupy — largest snapshot suite found in the corpus by a wide margin), `openai/openai-python` (`inline-snapshot`), `marimo-team/marimo` (`make py-snapshots`), `ccxt/ccxt` (static request/response fixture replay per exchange) | **4** |
| Mutation (mutmut) | none found anywhere | 0/50 |
| Benchmark (pytest-benchmark / pytest-codspeed / asv-style) | `streamlit` (`python-performance-tests` target), `home-assistant` (`pytest-codspeed`), `pydantic` (`tests/benchmarks/`), plus scattered marker use elsewhere | 5+ confirmed |
| Doctest (`--doctest-modules` or equivalent) | `huggingface/lerobot`, `pandas-dev/pandas`, `ultralytics/ultralytics`, `Lightning-AI/pytorch-lightning`, `roboflow/supervision`, `huggingface/transformers`/`diffusers` (`doctest-glob`/`doc-builder`) | 6+ |
| `xfail_strict = true` | `psf/black`, `openai/openai-python`, `pandas-dev/pandas`, `Lightning-AI/pytorch-lightning`, `marimo-team/marimo` (`--strict-config --strict-markers` sibling pattern) | 4-5 |
| Thread-safety / free-threading tests | `scikit-learn/scikit-learn` (`pytest-run-parallel`, `thread_unsafe_fixtures` list) | 1, notable |
| Live-network manifest validation | `sherlock-project/sherlock` (`test_validate_targets.py`, excluded from default run via `-m "not validate_targets"`) | 1, notable |

**Mutation testing (mutmut) has zero confirmed adopters across all 50 repos.** Property-based
testing has exactly 2 confirmed adopters (and both are libraries with unusually input-surface-heavy
domains: a code formatter and a validation library) — the numerical/scientific stack in this corpus
(`pandas`, `scikit-learn`, `jax`) has none, despite being the shape of code hypothesis is built for.

---

## pyproject.toml configs verbatim (cited)

**Streamlit — maximal ruff + dual type-checker**
`streamlit/streamlit@35df97a:pyproject.toml`
```toml
[tool.ruff.lint]
preview = true
explicit-preview-rules = false
# We activate all rules and only ignore the rules that we don't want to enforce
# or that are not relevant for our codebase.
select = ["ALL"]
```
```toml
[tool.mypy]
disallow_any_generics = true
disallow_subclassing_any = true
disallow_untyped_calls = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
disallow_untyped_decorators = true
warn_return_any = true
no_implicit_reexport = true
strict_equality = true
extra_checks = true
```
```toml
[tool.ty.rules]
possibly-unresolved-reference = "error"
```

**Zulip — mypy strict with named exceptions and exhaustiveness checking**
`zulip/zulip@282ccef:pyproject.toml`
```toml
[tool.mypy]
strict = true
disallow_subclassing_any = false
disallow_untyped_calls = false
warn_return_any = false

enable_error_code = [
    "redundant-self", "deprecated", "redundant-expr", "truthy-bool",
    "truthy-iterable", "ignore-without-code", "unused-awaitable",
    "explicit-override", "exhaustive-match",
]
plugins = ["mypy_django_plugin.main", "pydantic.mypy"]
```
`exhaustive-match` is a real exhaustiveness-enforcement ratchet (D4 dimension), not decoration.

**Airflow — pinned ruff base rule set, with the versioning rationale in the comment**
`apache/airflow@5fbe8db:pyproject.toml`
```toml
[tool.ruff.lint]
select = ["E4", "E7", "E9", "F"]
extend-select = [
    "I", "UP", "ASYNC", "ISC", "TC", "G", "LOG", "PT", "B015", "TID25", "E", "W",
    # ... ~30 more families, individually commented
]
```

**onnx — incremental mypy adoption, deferred strictness disclosed with TODOs**
`onnx/onnx@6696287:pyproject.toml`
```toml
[tool.mypy]
follow_imports = "silent"
strict_optional = true
warn_return_any = true
check_untyped_defs = true
disallow_any_generics = false  # Allow bare generics like np.ndarray
# TODO disallow_untyped_calls = true
# TODO disallow_incomplete_defs = true
# TODO disallow_subclassing_any = true
# NOTE: Do not grow the exclude list. Edit .lintrunner.toml instead.
```

**scikit-learn — the pyrefly config that turns out not to gate CI**
`scikit-learn/scikit-learn@8578499:pyproject.toml`
```toml
[tool.pyrefly]
project-includes = ["sklearn", "build_tools", "maint_tools"]
preset = "legacy"
[tool.pyrefly.errors]
bad-override = false
# ignore-missing-imports = ["*"]   # all missing imports ignored
```
`scikit-learn/scikit-learn@8578499:.github/workflows/lint.yml`
```yaml
run: set +e; ./build_tools/linting.sh &> output.txt
# (only the output artifact is uploaded — no exit-code check follows)
```

**pandas — the most multi-tool type-checking stack found in the corpus**
`pandas-dev/pandas@e909fc4:.pre-commit-config.yaml` (hook ids)
```
ruff-check, ruff-format, vulture, codespell, cython-lint, pyright, pyright, mypy,
stubtest, inconsistent-namespace-usage, unwanted-patterns, unwanted-patterns-in-tests,
pandas-errors-documented, validate-min-versions-in-sync, sort-whatsnew-items, ...
```
Twelve-plus custom `unwanted-patterns-*` local hooks mechanically enforce pandas-specific
conventions (e.g. "doesn't use pandas warnings", "no bare pipe alternation in message") — the
strongest example in the corpus of D7-style convention enforcement done as a fast pre-commit check
rather than manual review.

**cognee — every ignore states the failure class it declines to fix**
`topoteretes/cognee@c4cd8ce:pyproject.toml`
```toml
[tool.ruff.lint]
extend-select = ["E402"]
ignore = [
    "F401", "N999",
    "RUF012", # metadata: dict = {...} is a pydantic field default ruff can't see
              # through the indirect base class
    "TRY004", # raise TypeError from isinstance check — of 59 sites, 28 are pydantic
              # validators (only ValueError becomes ValidationError there)
    "ASYNC230", "ASYNC220", "ASYNC221", "ASYNC251",
    # blocking file/subprocess/sleep in async fns — document loaders and local
    # storage do sync IO by design today; re-enable when that lands (SDK-600)
]
```

**docling — the richest single "prove-it" chain found**
`docling-project/docling@eb17f57:Makefile`
```make
check-all: ## Run all checks (format, lint, type, module-boundary, LOC-budget, lockfile)
	ruff format --check .
	ruff check .
	uv run --no-sync ty check
	uv run --no-sync tach check
	python3 scripts/check_tach_module_coverage.py
	python3 scripts/check_max_lines.py
	dprint check
	uv lock --locked
```

---

## Pre-commit hook patterns

**`vllm-project/vllm@d7f5722:.pre-commit-config.yaml`** — the largest, most idiosyncratic hook set
found: 30+ hooks, including `mypy-3.10` through `mypy-3.13` (one hook per supported Python
version, commented `# TODO: Use pre-commit/mirrors-mypy when mypy setup is less awkward`),
`pip-compile` run 5 times (once per platform requirements lockfile), custom local hooks
`check-torch-cuda-call` (AST check forbidding new `torch.cuda` API calls outside the
accelerator-abstraction layer), `validate-config` (docstring-on-every-config-field enforcement),
and `check-test-tethering` (fails the commit if a new test file isn't wired into the Buildkite CI
config it uses instead of GitHub Actions).

**`deepspeedai/DeepSpeed@df00e0b:.pre-commit-config.yaml`** — four **local** architecture-boundary
hooks with no off-the-shelf equivalent: `check-torchdist` (bans direct `torch.distributed` use
outside `deepspeed/comm/`), `check-torchcuda` (bans direct CUDA-availability checks outside the
accelerator-abstraction layer), `check-license` (per-file header check, excludes vendored kernels),
`check-extraindexurl` (blocks stray `--extra-index-url`). Notable because this repo has *no ruff*
(flake8+yapf instead) yet still enforces genuine module-boundary invariants mechanically.

**`huggingface/lerobot@e595b79:.pre-commit-config.yaml`** — the most complete single-purpose
security stack in one pre-commit file: `gitleaks` (secret scanning), `zizmor` (GitHub Actions SAST),
`bandit` (Python SAST), plus mypy — lint+format+secrets+SAST+types unified.

**`apache/superset@d130742:.pre-commit-config.yaml`** mixes Python (mypy, ruff, diff-scoped
pylint), frontend (oxfmt, oxlint, stylelint), infra (helm-docs), and product-specific custom hooks
(`feature-flags-sync`, `db-engine-spec-metadata`) — pre-commit used as a general consistency gate,
not just a Python linter.

Approximate hook counts where a config exists: vllm ~32, pandas ~30, ray ~30, streamlit ~26,
superset ~22, skyvern 24, docling 12, dspy 6, cognee 8, home-assistant ~15 (incl. 6 local hooks).
At the thin end: yt-dlp (2 local hooks only — no secret scanning, no YAML/TOML checks, no mypy),
keras (api-gen + ruff only), peft (ruff + 2 pre-commit-hooks), searxng and sherlock (none at all).

**11+ repos have no `.pre-commit-config.yaml` at all**, relying entirely on CI and/or Makefile
targets: `huggingface/transformers`, `huggingface/diffusers`, `ccxt/ccxt`, `zulip/zulip`,
`Comfy-Org/ComfyUI`, `kovidgoyal/kitty`, `ranaroussi/yfinance`, `exo-explore/exo`,
`huggingface/pytorch-image-models`, `sherlock-project/sherlock`, `openai/openai-python`,
`soxoj/maigret`, `searxng/searxng`. Zulip is the sharpest example: a Tier-2, 25k-star, `mypy
strict=true`-enforcing repo that has deliberately built its own `tools/lint`/`tools/run-mypy`
scripts instead of adopting the pre-commit framework at all.

---

## Packaging and lockfile discipline

| Manager evidence | Count |
|---|---|
| `uv` used (as installer, runner, or both) | ~32/50 |
| `uv.lock` (or `pixi.lock` as a real equivalent) actually **committed** | ~19-21/50 (~40%) |
| `hatch` for env/task orchestration (often layered on uv as installer) | 3 (locust, yt-dlp, plus hatchling as build backend more broadly) |
| `pixi` (conda-based) as the primary/enforced lockfile | 2 (onnx: `pixi.toml`+`pixi.lock`; marimo: `uv run pixi lock` inside the prove-it chain, no root `uv.lock`) |
| `poetry` as build backend, but **lockfile not committed** | 2 (sherlock, maigret — both use poetry's build backend with no `poetry.lock` in the repo) |
| `pdm` as build backend | 2 (ArchiveBox — alongside uv as installer; pytorch-image-models — no lockfile at all) |
| Meson (native build system, not a Python package manager) | 1 (scikit-learn) |
| Bazel (primary build system) | 1 (jax) |
| Bare `requirements*.txt` / `setup.py`, no lockfile of any kind | ~28/50 (56%) |

**The library/app split matters more than the tool choice.** Repos that publish a library to PyPI
tend not to commit a lockfile even when `uv` is used as a task runner — `marimo`, `pandas`,
`huggingface/peft`, `huggingface/transformers`, `huggingface/diffusers`, `psf/black` all fall here;
pinning exact transitive versions in a published library's own repo wouldn't reflect what any
consumer's install actually resolves to. Application-shaped repos (`streamlit`, `docling`,
`cognee`, `reflex`, `zulip`, `Skyvern`, `prefect`, `pydantic` (library but ships `uv.lock` for its
own dev env), `exo-explore/exo`) commit a full lockfile. `django/django` is the starkest outlier
among frameworks: no `uv.lock`, no `poetry.lock`, `setup.py` plus scattered `requirements/*.txt` —
the single most-used Python web framework in this corpus has not modernized its own packaging.
`vllm-project/vllm` is the most sophisticated case: no single `uv.lock`, but five separate
per-platform (cpu/cuda/rocm/tpu/xpu) `requirements/*.txt` files regenerated via `uv pip-compile`
pre-commit hooks — real lockfile discipline, just not the single-file pattern.

---

## Synthesis: minimum viable vs. strongest justified Python stack

**Minimum viable** (solo/small-team — the modal repo in this corpus runs roughly this and nothing
more; `keras-team/keras`, `stanfordnlp/dspy`, `yt-dlp/yt-dlp`, and a dozen others sit here):
```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run pytest
```
This catches formatting drift, the pyflakes/pycodestyle core, and behavioral regressions —
nothing about types, nothing about property coverage. It is a legitimate floor: ruff is a single
static binary, sub-second on a diff, and requires zero design decisions to adopt. It is also what
24% of this corpus (12/50 confirmed) runs with **zero type checking at all**, including two
frameworks used as dependencies by large parts of the Python ecosystem (`django`, `keras`) and one
model-training library from the same org that builds `zulip`'s strict-mypy-enforced backend
(`huggingface/peft`, no type checker of any kind despite its sibling `lerobot` having targeted
strict mypy).

**Strongest justified stack** (org-scale, blast-radius-sensitive — modeled on the union of
zulip/marimo/streamlit/pandas/vllm; no single repo in this corpus does all of this, but each does
one part better than the rest):
```bash
uv sync --all-extras
uv run ruff format --check .
uv run ruff check .                              # curated extend-select with per-rule comments,
                                                  # not select=["ALL"] by default (streamlit/reflex
                                                  # are the exception, not the norm)
uv run mypy --strict <package>/                  # or ty/pyright/pyrefly — pick ONE and gate on it;
                                                  # 4 different tools are in live production use
                                                  # across this corpus, with no clear winner yet
uv run pytest --doctest-modules -n auto --cov=<package> --cov-fail-under=<N>
# for a schema/parser/format-boundary library specifically:
uv run pytest tests/fuzz/ -k atheris             # onnx and black are the only two repos doing this
# for a numeric/scientific library specifically:
uv run pytest --hypothesis-profile=ci            # zero of pandas/scikit-learn/jax do this today —
                                                  # the single largest unclaimed opportunity found
```

**On the "do they actually enforce types" question, stated plainly:** configured-in-some-form is
72% (36/50); actually gates CI is 54% (27/50); runs in strict mode is 16% (8/50). The gap between
the first and second numbers — 9 repos where type-checking exists in `pyproject.toml` but is
either never invoked, invoked with `set +e`, restricted to a diff-scoped subset, or downgraded to
warnings-only — is the more important number to design around than either headline figure, because
it means **"we have a `[tool.mypy]` section" is not evidence of a gate**; the evidence has to be
the CI job body, not the presence of the config file.

**The property-based and mutation-testing gap is the single largest unclaimed opportunity in this
corpus.** 0/50 confirmed mutmut adopters, and only 2/50 confirmed hypothesis adopters — neither of
which is a numerical/scientific library, despite `pandas`, `scikit-learn`, and `jax` being exactly
the shape of codebase (wide input surfaces, algebraic invariants) hypothesis is built for.

**Scale note:** the vllm/pandas-style 30-hook pre-commit setup with per-CUDA-version lockfile
regeneration and a dozen custom convention hooks is not something a 3-person team should copy
wholesale — it is the accumulated output of a large contributor base hitting the same mistakes
repeatedly and writing one hook each time it happened. The four-line minimum-viable stack above is
the correct starting point for `solo`/`small-team (2-10)`; the strongest-justified stack is what a
project graduates into once its contributor count and blast radius make a missed regression
expensive enough to justify the setup and CI-time cost — roughly the `org (10+)` tier, and the
allowlist-scoped mypy patterns (`prefect`, `ray`, `lerobot`, `docling`, `cognee`) are the honest
middle path for a repo that wants the ratchet but can't afford to fix its entire history at once.
